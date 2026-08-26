# Shared plumbing (`dtm_core.py`)

Reuse these rather than reinventing them in a new country's `dtm_*.py`:

- `_download_with_retries(download)` — exponential backoff on 429/5xx/
  timeouts, honoring `Retry-After`. Use for any single-request-per-chunk
  fetcher (pattern 2). Raises immediately on a `RuntimeError` from
  `download` (treated as a real out-of-coverage/bad-body response, not a
  transient failure).
- `_bbox_geom_lonlat(bbox, crs)` — reprojects a bbox to lon/lat for spatial
  catalog queries (STAC/WFS/Atom bounding-box filters).
- `fetch_tile_grid` / `tile_specs` — tiling, concurrency (8 workers), and
  disk-reuse logic for pattern 1 only.
- `NATIVE_RES` (5.0 m), `NODATA` (-9999.0), `SEA_SENTINEL` (-8888.0,
  ICGC-specific — don't assume it applies to a new source) constants.

## Countries that roll their own retry loop instead

`spain/dtm_cnig.py`, `france/dtm_rgealti.py`, `austria/dtm_bev.py`, and
`switzerland/dtm_swissalti.py` don't use `_download_with_retries` — they
need either a session-based retry (CNIG's custom retryable-status set) or
`Range`-resumable streaming for large archives, which
`_download_with_retries` doesn't provide. Reach for `_download_with_retries`
first; only write a custom retry loop if you specifically need session reuse
or Range-resume.

## Nodata/sea-sentinel handling

Every fetcher must handle the source's nodata/sea sentinel explicitly — see
the "Common mistakes" table in SKILL.md. In practice:
- Patterns 3 and 4 typically rewrite nodata to a fixed sentinel (`-9999.0`)
  during local conversion/resampling.
- Pattern 2's server-resampled sources either carry their own nodata tag
  through untouched (AHN) or need one added post-hoc (3DEP's exact-`0.0`
  ocean cells, which are real elevation, not nodata, in the raw response).
