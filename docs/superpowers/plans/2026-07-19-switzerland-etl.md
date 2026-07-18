# Switzerland ETL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a verified Switzerland chunk, density, and restriction ETL using swisstopo/FOEN open federal geodata.

**Architecture:** A focused swissALTI3D STAC client downloads official 2 m COGs and returns nodata-aware 5 m derived tiles from a persistent cache to the existing shared raster pipeline. Thin country CLIs forward one national EPSG:2056 region and three normalized FOEN overlay sources into existing shared ETL code.

**Tech Stack:** Python 3.12, requests, rasterio, pyproj, geopandas, pytest, React i18n catalogues.

## Global Constraints

- Run Python only through `uv run`.
- Use swissALTI3D 2 m COG bulk tiles in EPSG:2056, normalized to the project's
  5 m processing resolution in a persistent country cache.
- Keep network access out of automated tests.
- Do not add country-specific Justfile wiring.
- New restriction highlights must be verbatim substrings of their tooltips.
- Keep each Python file below 500 lines and satisfy strict ruff, mypy, and vulture checks.

---

### Task 1: swissALTI3D source client

**Files:**
- Create: `tests/highliner/etls/chunk/test_dtm_swissalti.py`
- Create: `highliner/etls/chunk/dtm_swissalti.py`
- Modify: `highliner/etls/chunk/dtm.py`

**Interfaces:**
- Produces: `fetch_swissalti_tiles(bbox: Bbox, cache_root: Path, crs: str) -> list[Path]`.
- Consumes: shared `dtm.fetch_tiles` cache-source dispatch.

- [x] Write tests that feed two STAC pages with old/new snapshots and assert one newest 2 m EPSG:2056 COG per tile, plus a dispatch test that asserts bbox/cache/CRS forwarding.
- [x] Run `uv run pytest tests/highliner/etls/chunk/test_dtm_swissalti.py -q` and confirm failure because the client/source does not exist.
- [x] Implement WGS84 bbox conversion, STAC pagination, newest-per-tile asset selection, atomic query caching, locked concurrent downloads, retries, full GeoTIFF validation, and nodata-aware 5 m normalization in `dtm_swissalti.py`; add `swissalti3d` to cached-source dispatch.
- [x] Run `uv run pytest tests/highliner/etls/chunk/test_dtm_swissalti.py -q` and confirm all tests pass.
- [x] Refactor only after green and rerun the focused tests.

### Task 2: country adapters

**Files:**
- Create: `tests/highliner/etls/chunk/test_switzerland.py`
- Create: `highliner/etls/chunk/switzerland.py`
- Create: `highliner/etls/density/switzerland.py`

**Interfaces:**
- Produces: `python -m highliner.etls.chunk.switzerland` and `python -m highliner.etls.density.switzerland`.
- Consumes: `shared.precompute` and `shared.build_country_density`.

- [x] Write adapter tests asserting `COUNTRY == "switzerland"`, the national bbox/CRS/source, worker forwarding, progress reporting, and density country forwarding.
- [x] Run the new adapter tests and confirm imports fail because the modules do not exist.
- [x] Implement the single-region chunk CLI and thin density CLI using the established Czechia/Italy argument shapes.
- [x] Run the adapter tests and confirm they pass.

### Task 3: FOEN restriction overlays and localized metadata

**Files:**
- Create: `tests/highliner/etls/restriction/test_switzerland.py`
- Create: `highliner/etls/restriction/switzerland.py`
- Modify: `highliner/core/restrictions.py`
- Modify: `frontend/src/lib/i18n/restrictionStrings.ts`

**Interfaces:**
- Produces: `ch_game_reserves`, `ch_bird_reserves`, and `ch_parks` parquet layers.
- Consumes: `shared.LayerBuildSpec` and `shared.write_layers`.

- [x] Write tests for source glob detection, atomic validated ZIP extraction, EPSG:2056-to-4326 loading, layer specs/name fields, and restriction metadata/highlight invariants.
- [x] Run the new restriction tests and confirm failure because the adapter and layer metadata do not exist.
- [x] Implement the three-source FOEN adapter and add English, Spanish, and Catalan display copy whose highlights are exact tooltip substrings.
- [x] Run Python restriction tests and `npm test -- --run frontend/src/lib/i18n/i18n.test.tsx` (through the existing frontend command shape) and confirm green.

### Task 4: real smoke, verification, and delivery

**Files:**
- Modify: `COUNTRIES.md`

**Interfaces:**
- Produces: issue evidence, one verified commit, and a PR closing issue #47.

- [x] Use the real client on a small Lauterbrunnen-area core/halo bbox, run shared chunk processing, inspect raster resolution/nodata and resulting anchor/pair parquet, and post command/results to issue #47.
- [x] Run all three module `--help` commands, focused Switzerland tests, `just test`, and `just check`; fix failures with a failing regression test first.
- [x] Mark Switzerland `[P]` in `COUNTRIES.md`, commit all implementation, and post the commit SHA/adapters/layers to issue #47.
- [x] Request read-only code review for the branch diff; fix Critical/Important findings and rerun verification.
- [ ] Push `etl/switzerland-47`, open a PR to the default branch with source, resolution, method, restrictions, 80,500 km2/805-chunk coverage summary, and `Closes #47`.
- [ ] Post verification evidence and the PR link to issue #47.
