# Remove the single-region path; keep only chunked precompute

Date: 2026-07-07

## Goal

The chunked precompute path introduced in
[2026-06-14-precompute-catalonia-anchors-design.md](2026-06-14-precompute-catalonia-anchors-design.md)
was added *alongside* the original single-region path (`highliner ingest` +
`analyze`, serving live off a persisted `mosaic.tif`). It is now the only
path actually used in practice (`data/catalonia` is the only region on disk,
and it's chunked). This spec removes the single-region path entirely and
generalizes the chunked path's naming — it's no longer Catalonia-specific
code, just region-agnostic precompute logic that happens to have been used
for Catalonia so far.

No data migration is needed: `data/catalonia` already uses the chunked
layout.

## CLI surface

Remove `ingest` and `analyze`. Rename `precompute-catalonia` → `precompute`,
generalized to any region:

    highliner precompute --region NAME --bbox minx,miny,maxx,maxy [--chunk-km 10] [--data-dir ...]
    highliner precompute-density --region NAME [--data-dir ...]
    highliner serve [--host ...] [--port ...]
    highliner fetch-restrictions

`--bbox` becomes **required** on `precompute` (no more implicit
`config.CATALONIA_BBOX` default) — drop `CATALONIA_BBOX` from
`highliner/core/config.py`. `--region` becomes required on
`precompute-density` too (drop its `default="catalonia"`), for the same
reason: nothing in the CLI should default to a specific region anymore.

## Module renames

Logic is unchanged — this is a rename/de-scoping, not a rewrite:

- `highliner/services/catalonia.py` → `highliner/services/precompute.py`
  - `precompute_catalonia(bbox, data_dir, chunk_m, report)` →
    `precompute(region, bbox, data_dir, chunk_m, report)` — the region name
    was implicitly `"catalonia"` before (hardcoded as `region_dir = Path(data_dir) / "catalonia"`
    in `precompute_catalonia`); it becomes an explicit parameter.
  - `chunk_grid`, `_in_core`, `process_chunk` are unchanged internally, only
    `process_chunk`'s caller passes a region-derived `region_dir` instead of
    a hardcoded one.
- `highliner/repositories/catalonia_store.py` → `highliner/repositories/chunked_store.py`
  - `Grid`, `read_grid`, `chunk_indices_for_bbox`, `load_anchors_in_bbox`,
    `load_pairs_in_bbox` unchanged (they already take `region_dir` as a
    parameter, so nothing Catalonia-specific to remove here beyond the
    module name and its docstring's example path).

## Repository cleanup (`highliner/repositories/dtm.py`)

Delete:
- `fetch_dtm` — built one big persisted `mosaic.tif` per region; only used by
  the removed `ingest` CLI command.
- `mosaic_bounds_lonlat` — read a `mosaic.tif`'s extent; only used by the
  removed single-region branch of `router/regions.py`.

Keep: `fetch_tiles`, `raster_from_tiles`, `tile_specs`, `estimate_tiles`,
`_snap`, `_download_tile` — these are what `process_chunk` uses internally
per-chunk (download a haloed window's tiles, merge to an in-memory `Raster`,
discard). `NATIVE_RES`, `MAX_TILE_PX`, `NODATA`, `SEA_SENTINEL`,
`ICGC_WCS`, `COVERAGE_ID` all stay — still load-bearing for the tile fetch.

## Model cleanup (`highliner/models/raster.py`)

Delete the `Raster.open()` classmethod and its `SEA_SENTINEL` class
attribute. Both existed to read a *persisted* `mosaic.tif` back off disk —
only used by the removed `analyze` CLI command and the removed
`router/deps.py::load_region`. `dtm.py::raster_from_tiles` already does its
own sea-sentinel masking independently (a module-level `SEA_SENTINEL`
constant in `dtm.py`, distinct from this one) when merging tiles in memory,
so nothing else depends on `Raster.open`.

`Raster` itself (the dataclass — `data`, `transform`, `res`, `value_at`,
`sample_line`) is unchanged and stays central: it's what
`dtm.raster_from_tiles` returns and what `extract_anchors`/`find_candidates`
operate on during precompute.

## Router simplification

Every region now has `grid.json` (there is no other kind of region), so the
`is_chunked_layout` branch disappears everywhere it appears:

- **`router/zones.py`** — always: parse bbox → `chunked_store.load_pairs_in_bbox`
  → `filter_candidates` → `build_zones`. Delete the `else` branch
  (`load_region` + `find_candidates` against a live raster).
- **`router/anchors.py`** — always: `chunked_store.load_anchors_in_bbox` →
  `anchors_in_view`. Delete the `else` branch.
- **`router/deps.py`** — delete `_load_region`, `load_region`, and
  `is_chunked_layout` (all three only served the removed branches). Keep
  `anchors_in_view`, `get_data_dir`, `parse_bbox_utm`, `parse_bbox_lonlat`.
- **`router/regions.py`** — delete the `elif (p / "anchors.parquet").exists()`
  branch and its `mosaic_bounds_lonlat` import; every region directory is
  identified by `grid.json` and its bounds come from `_bounds_from_grid`.

## Test changes

- **Delete** `tests/test_ingest.py` (tested `dtm.fetch_dtm`, which no longer
  exists).
- **`tests/test_cli.py`** — drop the `ingest`/`analyze` command tests; rename
  the `precompute-catalonia` tests to match the new `precompute` command
  (region + bbox both explicit args now, no default-bbox assertion).
- **`tests/test_raster.py`** — drop the `Raster.open()` test; keep the
  `value_at`/`sample_line` tests (construct `Raster` directly).
- **`tests/test_deps.py`** — drop `load_region`/`is_chunked_layout` tests.
- **`tests/test_api.py`**, **`tests/test_integration.py`** — these currently
  build a fixture region by writing a bare `mosaic.tif` + `anchors.parquet`
  directly to disk (bypassing the CLI) and hitting the API. Rewrite the
  fixtures to instead build a minimal chunked region (`grid.json` +
  `anchors/p_0_0.parquet` + `pairs/q_0_0.parquet`), since that's the only
  layout the API supports afterward.
- **Rename** `tests/test_catalonia.py` → `tests/test_precompute.py`,
  `tests/test_catalonia_store.py` → `tests/test_chunked_store.py`, updating
  imports (`highliner.services.precompute`,
  `highliner.repositories.chunked_store`) and the now-explicit `region`
  argument to `precompute()`.

## Out of scope

- Renaming the `data/catalonia` directory itself, or anything about the data
  currently on disk — it already matches the (only, now) supported layout.
  `"catalonia"` remains a perfectly ordinary region name, just no longer
  special-cased in code.
- Adding new regions / new DTM or restrictions sources (see `NEW_LOCATIONS.md`
  for that separate effort).
- Any change to the precompute algorithm itself (chunking, halo, ownership,
  envelope) — this spec is a deletion + rename, not an algorithm change.
