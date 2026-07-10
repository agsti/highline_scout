# Adding a new location

What's needed to add a new region to the pipeline, based on the current
architecture (see AGENTS.md for the full picture).

## 1. A DTM (elevation) source

`highliner/repositories/dtm.py` is currently written against one specific WCS
API shape (small tiled `GetCoverage` requests merged in memory per chunk). A
new location needs a terrain source that provides:

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
map overlay feature. The current layers (`zepa`/`zec`/`enp`) are built from
MITECO's national Banco de Datos de la Naturaleza files, so any new location
*within Spain* is already covered — no new restrictions work is needed. For a
location outside Spain:

- Needs a source (WFS, bulk download, etc.) serving protected-area polygons
  with a license permitting reuse.
- Layer/attribute schema will very likely differ from the current national
  `zepa`/`zec`/`enp` split — expect to rewrite the layer-derivation logic,
  not just point it at a new URL.
- Label/tooltip text is currently hardcoded server-side in the source
  language (English); a new location needs its own translated strings (see
  AGENTS.md's i18n section for how the three-language catalogs and the
  `RESTRICTION_STRINGS` fallback chain work).

## 3. Coordinate system

`highliner/core/config.py`'s `UTM_CRS` is a single global constant, used by
`core/geo.py`'s cached transformer, `dtm.py`'s DTM request CRS, and the
raster/zone models. A new location needs:

- Its own appropriate projected CRS (a UTM zone or equivalent metric
  projection covering it with acceptable distortion).
- If it doesn't share a CRS with existing regions, `UTM_CRS` can no longer
  be a single hardcoded constant — it needs to become a per-region value
  (e.g. stored alongside `grid.json`), threaded through `geo.py`, `dtm.py`,
  and the serializers instead of assumed global.

## 4. Precompute strategy

There is only one supported pattern — chunked precompute
(`services/precompute.py`, `highliner precompute --region NAME --bbox ...`):
tiles the region into `CHUNK_M`-sized squares (with a halo so
`MAX_PAIR_LEN`-long pairs crossing chunk edges are still found), and for each
chunk downloads DTM tiles, extracts anchors, runs pairing at a loose envelope
(`PRECOMPUTE_*` config values) so exposure is baked into every stored pair,
writes `anchors/p_{cx}_{cy}.parquet` + `pairs/q_{cx}_{cy}.parquet`, then
**deletes the raw DTM tiles** — no raster persists on disk at all. `/zones` and
`/anchors` always read from this layout (`repositories/chunked_store.py`) and
just filter precomputed pairs against the live slider thresholds
(`services/pairing.filter_candidates`) — cheap, no raster touched at request
time.

`precompute()` already takes `region` as an explicit parameter, so adding a new
location is just calling it with a new region name and bbox — no code changes
needed here, only a working DTM source (§1) for that bbox.
