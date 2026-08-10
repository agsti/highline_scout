# Tiled 3DEP export

## Problem

`highliner/etls/chunk/united_states/dtm_3dep.py` issues **one**
`exportImage` request per chunk: a chunk's halo bbox is 10000 + 2×1050 =
12100 m, which at the 5 m analysis grid is a 2420×2420 px export. Over terrain
with dense, overlapping lidar coverage, server-side mosaicking of that footprint
takes longer than the ~90 s budget of the CloudFront distribution in front of
the ImageServer, which returns a 504 HTML body. `response.raise_for_status()`
turns that into an `HTTPError`, the chunk fails, and
`shared._check_parallel_results` aborts the whole region run.

Confirmed on the California run, chunk `26,58` (EPSG:5070 core
`-2097000, 1823000` → `-2087000, 1833000`; roughly 37.05–37.16 N,
120.06–119.98 W, Sierra Nevada near Yosemite). It has failed on every attempt —
2026-07-28, 2026-07-30 and 2026-08-10 — leaving three empty
`data/united_states/california/tiles/chunk_26_58_<pid>/` directories, one per
run. California is otherwise complete: 8711 of 8712 chunks written.

Measurements taken 2026-08-10 against the live service:

| Request | Result |
| --- | --- |
| chunk 26,58 full 2420² @5 m | **504 after ~90 s**, repeatably |
| chunk 26,57 full 2420² @5 m (neighbour, already written) | 200 TIFF after **60.5 s** |
| chunk 26,58 same footprint @10 m (1210²) | 200 TIFF, 3.8 s |
| chunk 26,58 SW quadrant @5 m (1210²) | 200 TIFF, **12.5 s** |
| chunk 26,58 NE quadrant @5 m (1210²) | 200 TIFF, **9.4 s** |

The footprint is servable; the single full-size request is not. The mosaic
catalog (`ImageServer/query`, `returnCountOnly`) reports ~50 overlapping source
items over 26,58 and 51 over 26,57 — dense overlapping lidar projects that are
expensive to blend. 26,57 cleared the ~90 s bar at 60.5 s; 26,58 sits just over
it. That is why the failure is deterministic rather than flaky.

Two secondary findings:

* `MAX_EXPORT_PX = 8000` guards the wrong quantity. The binding limit is
  time-to-mosaic, and it bites at ~2400 px over dense terrain — nowhere near
  8000 px.
* Edge-caching of the 504 was investigated and **ruled out** as a factor. One
  repeat returned a cached 504 in 0.1 s, but repeats generally cost a full
  ~90 s, so `_download_with_retries` is not systematically defeated; it just
  burns ~4 × 90 s before giving up. A cache-busting nonce param is accepted by
  the server but buys nothing. No change to shared retry logic is warranted.

This is not California-specific. `_region()`
(`united_states/main.py:40`) wires `dtm_3dep.fetch` into all 51 US regions
(50 states + DC), so any state with dense lidar over steep terrain can hit it —
Colorado, Washington, Utah, Idaho and Wyoming are likely candidates. Alabama,
Alaska, Arizona and Arkansas completed because their footprints happened to
stay under the budget, not because they are immune.

## Goal

Keep every 3DEP export comfortably under the gateway's time budget by splitting
each chunk's halo bbox into a grid of smaller `exportImage` requests, merged
back into one raster — without weakening the guarantee that a region reporting
"completed" really did fetch every chunk.

Out of scope: the abort-on-failure policy in `shared.py` (deliberately kept, see
below), the shared retry logic in `dtm_core.py`, and every other country's DTM
adapter.

## Scope

Changes are confined to two files:

* `highliner/etls/chunk/united_states/dtm_3dep.py`
* `tests/highliner/etls/chunk/united_states/test_dtm_3dep.py`

`dtm_3dep` has exactly two non-test importers, both US-only:
`united_states/main.py:15` (import) and `:40` (wiring into every `Region`). No
shared module is modified, so Spain, Netherlands, Poland, France, Italy, UK,
Austria, Switzerland, Czechia and Chile are provably untouched.

## Design

### Reuse `fetch_tile_grid`, with one deliberate deviation

`dtm_core.fetch_tile_grid` already does what is needed: split a bbox on the 5 m
grid, download tiles concurrently (`TILE_WORKERS = 8`), retry transient HTTP
failures per tile, reuse tiles already on disk, and return the paths.
`shared.process_chunk` already feeds the result to `raster_from_tiles`, which
merges any number of tiles. Spain's `dtm_icgc.fetch` is the existing precedent.

The deviation is in error handling. `fetch_tile_grid`'s inner `fetch_one`
catches `RuntimeError` and **silently drops that tile**
(`dtm_core.py:136`), returning a partial list. For ICGC that is correct: parts
of the Catalonia bbox genuinely fall outside coverage. For 3DEP it would be
harmful. The ImageServer never errors on extent — it fills out-of-coverage
footprints from neighbouring data — so a non-raster body means a real failure,
not missing coverage. Dropped silently, it would produce a hole in the merged
raster, anchors extracted from incomplete terrain, a written partition, and a
chunk marked permanently done. That is exactly the silent-hole failure this
pipeline must not have.

Therefore `_download_tile` raises a module-local `ExportError(Exception)`
instead of `RuntimeError`. `fetch_tile_grid` does not catch it, so it
propagates out of `pool.map` and fails the chunk. It also passes through
`_download_with_retries` untouched, which catches only
`requests.RequestException` — preserving today's "a bad body is not retried"
behaviour.

### Tile size: 1210 px

Every interior US chunk's halo bbox is 12100 m = 2420 px at 5 m. `tile_px`
must divide that evenly or `tile_specs` emits slivers: 1200 would tile it as
1200 + 1200 + 20, giving nine tiles including two useless 20 px strips.
**`TILE_PX = 1210`** splits it into exactly **2×2**, and is precisely the size
benchmarked above at 9–12.5 s per tile — so the sizing rests on measurement
rather than extrapolation. Edge chunks, whose cores are clipped to the region
bbox, simply produce smaller grids.

All four tiles download concurrently — `fetch_tile_grid` sizes its pool at
`min(TILE_WORKERS, len(specs))`, so four here — meaning a dense chunk that
previously took 60 s (or timed out) should complete in roughly the time of its
slowest tile.

### Resulting module shape

```python
TILE_PX = 1210    # 2x2 per chunk; keeps each export under the ~90s gateway budget

class ExportError(Exception):
    """A non-raster export body — must fail the chunk, never drop a tile."""

def _download_tile(bbox, width, height, dest, *, epsg) -> Path:
    # exportImage GET -> TIFF magic check (else ExportError) -> _write_masked

def fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]:
    epsg = int(crs.rsplit(":", 1)[-1])
    return fetch_tile_grid(bbox, tiles_dir,
                           functools.partial(_download_tile, epsg=epsg),
                           ext="tif", tile_px=TILE_PX)
```

`fetch_tile_grid` calls `download(bbox, w, h, dest)` positionally, so binding
the region EPSG with `functools.partial` keeps `_download_tile` module-level
and signature-compatible. The partial is built inside the worker process; only
`dtm_3dep.fetch` itself is pickled into `shared`'s process pool, and that stays
a module-level function.

`_write_masked` is unchanged. The ocean-`0.0` → `SEA_SENTINEL` remap simply
moves from once-per-chunk to once-per-tile; the semantics are identical because
the test is per-cell.

Removed: `fetch_3dep` (superseded by `_download_tile`), `_pixel_dims` (now
`tile_specs`' job), and the `MAX_EXPORT_PX` runtime guard. `tile_specs`
provably caps width and height at `tile_px`, so the guard is dead code.
`MAX_EXPORT_PX` is retained only as a documented constant recording the ArcGIS
hard cap, with a note that the real limit is time, not pixels.

### Seam correctness

`tile_specs` snaps the bbox outward to the 5 m grid and each request's `size`
is the extent divided by 5, so every tile's pixel boundaries land on the same
global 5 m lattice in the region CRS. `raster_from_tiles` merges with
`bounds=halo_bbox`, clipping the snapped overshoot back. Tiles therefore
compose exactly, with no resampling mismatch at the seams despite each tile
being resampled server-side independently. This is verified empirically rather
than assumed (see below).

### Failure policy: unchanged

A chunk that still fails after tiling continues to raise, and
`shared._check_parallel_results` continues to abort the region. This is
deliberate. It is the property that makes a region's "completed" line
trustworthy — it is what allowed Alabama, Alaska, Arizona and Arkansas to be
certified as genuinely complete. `just` restarts the region and the resume path
skips finished chunks, so the cost of the policy is low once failures are rare.

## Testing

Unit tests, replacing the four that reference removed functions
(`test_pixel_dims_render_the_bbox_at_5m`,
`test_fetch_3dep_masks_ocean_and_builds_the_export_request`,
`test_fetch_3dep_rejects_a_non_raster_body`,
`test_fetch_3dep_guards_the_export_pixel_cap`). The two that exercise `fetch`
rather than `fetch_3dep` — `test_fetch_wraps_the_call_in_the_transient_retry`
and `test_fetch_ignores_cache_dir_and_extracts_the_epsg` — keep their intent
but need their single-request assumptions updated:

* `fetch` splits a 12100 m halo bbox into exactly four tiles and returns four
  paths
* request params are correct: `bbox`, `size`, and `bboxSR`/`imageSR` derived
  from the region CRS, including Alaska's EPSG:3338
* ocean `0.0` becomes `SEA_SENTINEL` while genuine elevations are untouched
* **a non-TIFF body propagates out of `fetch` instead of dropping a tile** —
  the regression guard for the `ExportError` deviation
* a per-tile `requests.Timeout` is retried

Empirical validation against the live service:

1. Fetch chunk 26,58 through the new path; it must succeed where the single
   full-size request 504s every time.
2. Fetch chunk 26,57 both ways — it is the neighbour that does work single-shot
   at 60.5 s — and assert the merged arrays are identical, proving the seam
   reasoning above.

Per the machine's memory constraints, pytest runs under `ulimit -v` and
`timeout`, using `.venv/bin/python` directly rather than `uv run`.

## Rollout

Re-run `just etl-chunk united_states 10` after merge. California skips its 8711
finished chunks and fetches only 26,58, so no one-off tooling is needed. The
four completed regions are unaffected: they are skipped wholesale by the resume
path, and DTM tiles are transient, so no stored data depends on the old fetch
path.
