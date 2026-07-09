# Reduce CNIG requests during Spain precompute

**Date:** 2026-07-09
**Where:** `highliner/repositories/dtm.py` (CNIG source path)
**Status:** design approved, pending spec review

## Problem

Precomputing the non-Catalonia Spain regions (all use `dtm_source="cnig"`)
triggers HTTP 429 "too many requests" from
`centrodedescargas.cnig.es`. Two properties of the current CNIG path cause it:

1. **Redundant per-chunk catalog queries.** Every `process_chunk` that isn't
   already finished calls `_fetch_cnig_tiles`, which calls
   `_cnig_query_sheets(session, bbox, crs)` — a *paginated* `archivosSerie`
   catalog request — to discover which MDT05 sheets intersect that chunk.
   Adjacent chunks resolve to the same sheets, so this query is almost entirely
   redundant, and its volume scales with chunk count × `--chunk-workers` ×
   `--jobs`.

2. **No throttle handling on CNIG calls.** Unlike the ICGC/IDEE tile path
   (`_download_with_retries` + `_retry_delay`), none of the CNIG requests
   (`_cnig_query_sheets`, `_download_cnig_sheet`) retry on 429/5xx. A throttle
   fails the chunk instead of backing off.

### Why it bites the current re-run

The immediate trigger is re-precomputing regions after the
`bearing_in_sectors` fix (`docs/2026-07-09-bearing-in-sectors-tol-bug.md`),
which deletes each region's `pairs/` partitions. `process_chunk` skips a chunk
only when its `pairs/q_*.parquet` exists, so deleting `pairs/` forces every
chunk to re-run. The MDT05 sheets are still cached on disk from the prior run,
so `_download_cnig_sheet` is all cache hits (0 requests) — meaning the paginated
catalog query is essentially the *entire* remaining request load. Caching it
removes nearly all requests in this scenario.

## Goals / non-goals

- **Goal:** eliminate the redundant per-chunk catalog queries (re-runs make
  ~0 catalog requests).
- **Goal:** make CNIG throttling non-fatal and polite (429-aware backoff).
- **Non-goal:** change concurrency defaults. `--chunk-workers` / `--jobs`
  remain operational knobs for controlling request *rate*.
- **Non-goal:** rearchitect the CNIG sheet discovery (the dead `_cnig_index`
  local-geometry path stays out of scope).

## Design

### Part 1 — Cache sheet resolution to disk

`_cnig_query_sheets(bbox, crs)` output depends only on `(bbox, crs)`. Chunk
grids are deterministic, so caching this result makes re-runs reuse it instead
of re-querying CNIG.

New helper in `dtm.py`:

```
def _cached_query_sheets(session, bbox, crs, cache_dir) -> list[tuple[str, str]]:
    key = sha1(json.dumps([crs, list(bbox)]).encode()).hexdigest()
    path = cache_dir / f"{key}.json"
    if path.exists():
        return [tuple(row) for row in json.loads(path.read_text())]
    sheets = _cnig_query_sheets(session, bbox, crs)
    tmp = path.with_suffix(f".json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(sheets))
    tmp.replace(path)            # atomic; concurrency-safe, no lock needed
    return sheets
```

- `cache_dir = _cnig_cache_root(tiles_dir) / "mdt05_sheet_index"`, created
  alongside the existing `mdt05_tiles/` cache. The cache lives with the data
  dir, so it survives across runs and is shared by all chunk processes.
- The key is `sha1(json.dumps([crs, list(bbox)]))`. The chunk grid emits
  identical halo bboxes each run (deterministic float arithmetic on the same
  region bbox / `chunk_m`), so the key is stable across runs.
- `_fetch_cnig_tiles` calls `_cached_query_sheets` instead of
  `_cnig_query_sheets` directly.
- Concurrency: one file per key, written atomically via tmp + `replace`. Two
  processes resolving the same key race harmlessly — last writer wins, content
  identical. No lock required.

An empty result (a chunk with no intersecting sheets, e.g. over the sea) is a
valid cache entry (`[]`) and is cached like any other, so empty chunks also stop
re-querying.

### Part 2 — 429-aware retry for CNIG calls

Add a retry wrapper reusing the existing backoff:

```
_CNIG_RETRY_STATUS = {429, 500, 502, 503, 504}

def _cnig_request(session, method, url, **kwargs):
    for attempt in range(TILE_RETRY_ATTEMPTS):
        try:
            r = session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            if attempt == TILE_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_retry_delay(attempt, exc.response))
            continue
        if r.status_code in _CNIG_RETRY_STATUS and attempt < TILE_RETRY_ATTEMPTS - 1:
            time.sleep(_retry_delay(attempt, r))
            continue
        return r
```

- Refactor `_retry_delay` to `_retry_delay(attempt, response=None)` (it only
  ever reads `response.headers["Retry-After"]`), and update its one existing
  caller in `_download_with_retries` to pass `exc.response`. Both the ICGC/IDEE
  and CNIG paths then share one backoff function that honors `Retry-After` and
  falls back to exponential backoff.
- Route the `session.get` calls in `_cnig_query_sheets` and the
  `detalleArchivo` / `initDescargaDir` gets in `_download_cnig_sheet` through
  `_cnig_request`.
- The streamed `descargaDir` POST: issue it via `_cnig_request` with
  `stream=True`, check `status_code` for the retry set *before* streaming the
  body; only stream once a non-retry status is returned. Keep the existing
  content-type guard and chunked write.
- Reuse `TILE_RETRY_ATTEMPTS` / `TILE_RETRY_BASE_S`. The existing
  `_cnig_sheet_geom` (index builder) already has ad-hoc 429 handling; leave it
  as-is (out of the precompute hot path).

## Testing

Offline unit tests (monkeypatch / fake session), matching existing test style:

1. **Cache helper — miss then hit.** Monkeypatch `_cnig_query_sheets` with a
   counter. First `_cached_query_sheets` call queries once and writes the JSON
   file; a second call with the same `(bbox, crs)` returns the same result with
   the query counter unchanged (no second HTTP). Assert the cache file exists.
2. **Cache helper — empty result cached.** Query returns `[]`; second call still
   makes no HTTP call.
3. **`_cnig_request` retry.** Fake session returns 429 then 200; assert the call
   returns the 200 response and that the sleep/backoff was invoked once. A fake
   returning 429 for all attempts surfaces the last response (caller's
   `raise_for_status` then raises).

## Rollout

No data migration. On the next re-precompute run the cache populates on first
touch per chunk; subsequent chunks and re-runs read it. Safe to delete
`data_dir/mdt05_sheet_index/` at any time (it just re-queries).
