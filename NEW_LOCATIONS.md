# Adding a new location

What's needed to add a new region to the pipeline, based on the current
architecture (see AGENTS.md for the full picture).

## 1. A DTM (elevation) source

`highliner/repositories/dtm.py` is currently written against one specific
WCS API shape (small tiled `GetCoverage` requests merged into a
`mosaic.tif`). A new location needs a terrain source that provides:

- Bare-earth elevation raster covering the target area, fine enough
  resolution to resolve cliff faces (current tuning assumes ~5 m; coarser
  data may need `SLOPE_MIN_DEG`/other `config.py` extraction params
  loosened).
- A way to fetch it programmatically (WCS/WMS tiled API, or a bulk
  download to pre-tile locally) — `dtm.py`'s tiling logic assumes a
  request-size-capped API and will need adapting if the new source has a
  different request shape or no cap at all.
- Known nodata/out-of-coverage behavior (sea, borders) so it can be masked
  correctly — don't assume the existing `SEA_SENTINEL` convention carries
  over; a new source may flag nodata differently (or ambiguously, e.g. with
  plain `0`).

## 2. A restrictions source (optional)

`highliner/repositories/restrictions.py` is informational — protected-area
overlays are not required for anchor/zone detection to work, only for the
map overlay feature. If added for a new location:

- Needs a WFS (or equivalent) serving protected-area polygons with a
  license permitting reuse.
- Layer/attribute schema will very likely differ from the current
  `zec`/`zepa`/`pein`/`parcs`/`fauna` split — expect to rewrite the
  layer-derivation logic, not just point it at a new URL.
- Label/tooltip text is currently hardcoded server-side in the source
  language; a new location needs its own translated strings (see AGENTS.md's
  i18n section for how the three-language catalogs and the
  `RESTRICTION_STRINGS` fallback chain work).

## 3. Coordinate system

`highliner/core/config.py`'s `UTM_CRS` is a single global constant, used by
`core/geo.py`'s cached transformer, `dtm.py`'s ingest/mosaic CRS, and the
raster/zone models. A new location needs:

- Its own appropriate projected CRS (a UTM zone or equivalent metric
  projection covering it with acceptable distortion).
- If it doesn't share a CRS with existing regions, `UTM_CRS` can no longer
  be a single hardcoded constant — it needs to become a per-region value
  (e.g. read from the region's own raster, or stored alongside
  `grid.json`/`mosaic.tif`), threaded through `geo.py`, `dtm.py`, and the
  serializers instead of assumed global.

## 4. Precompute strategy

Two existing patterns, pick one per new location:

- **Single-region** (`highliner ingest` + `analyze` CLI commands): produces
  one `mosaic.tif` + `anchors.parquet`. The DTM raster stays on disk and is
  loaded live at serve time (`router/deps.py::load_region`) — `/zones`
  computes pairing/exposure on every request by sampling the raster
  (`services/pairing.py`'s `raster.sample_line`). Simple, but keeps the
  raster resident and does live exposure sampling per request.
- **Chunked precompute** (the pattern `services/catalonia.py` implements):
  tiles the region into `CHUNK_M`-sized squares (with a halo so
  `MAX_PAIR_LEN`-long pairs crossing chunk edges are still found), and for
  each chunk downloads DTM tiles, extracts anchors, runs pairing at a loose
  envelope (`PRECOMPUTE_*` config values) so exposure is baked into every
  stored pair, writes `anchors/p_{cx}_{cy}.parquet` + `pairs/q_{cx}_{cy}.parquet`,
  then **deletes the raw DTM tiles** — no raster persists on disk at all.
  `/zones` detects this layout via `grid.json` (`is_chunked_layout`) and
  just filters precomputed pairs against the live slider thresholds
  (`filter_candidates`) — cheap, no raster touched at request time.

  This is the pattern to reuse for "precompute everything" on a new
  location: generalize `catalonia.py`'s chunking/ownership logic (it's
  currently named/scoped to one region) rather than building a new
  precompute path from scratch.
