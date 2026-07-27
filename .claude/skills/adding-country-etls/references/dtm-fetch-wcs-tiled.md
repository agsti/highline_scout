# Pattern 1: WCS, tiled (small per-request cap)

Use only when the WCS enforces a hard per-request pixel/byte cap that makes
a single request impossible. If there's no such cap, use
`dtm-fetch-single-request.md` instead — it's simpler.

**Reference implementation:** `spain/dtm_icgc.py` (ICGC).

WCS 1.0.0 `GetCoverage`, ArcGrid format, capped at ~140 KB (~35,800 px) per
response. Uses `dtm_core.fetch_tile_grid` to split the bbox into a grid of
≤175x175 px tiles, downloads concurrently (8 workers) into the transient
`tiles_dir`, and merges them later. Nothing persists to `cache_dir` — tiles
are transient and deleted with the chunk.

Reuse from `dtm_core.py`:
- `fetch_tile_grid` — handles the tiling, concurrency, retry, and
  reuse-on-disk logic; you only supply a `download(bbox, width, height, dest)`
  callback that issues one tile's `GetCoverage` request.
- `tile_specs` — computes the tile grid if you need it standalone.
