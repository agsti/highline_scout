# Portugal ETL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add chunk, density, and protected-area ETLs for mainland Portugal.

**Architecture:** The chunk adapter uses DGT's 2 m bare-earth LiDAR terrain tiles in EPSG:3763. A module-level fetcher authenticates to DGT's CDD STAC API using environment credentials, caches downloaded GeoTIFF sheets, and returns sheets intersecting each chunk. The restrictions adapter downloads Portugal's ICNF WFS layers for Birds Directive ZPE, Habitats Directive SIC/ZEC, and the national RNAP network.

**Tech Stack:** Python 3.12, requests, rasterio, pyproj, GeoPandas, FastAPI ETL conventions.

## Global Constraints

- Use `COUNTRY = "portugal"` and only mainland Portugal because DGT's current LiDAR coverage is mainland-only.
- Require `DGT_CDD_USERNAME` and `DGT_CDD_PASSWORD`; never persist credentials in the repository or cache.
- Use DGT `MDT-2m` (bare-earth) in EPSG:3763 and mask its declared nodata metadata through rasterio.
- Add one unique `np.int16` density restriction bit for each Portugal-specific layer.

---

### Task 1: Portuguese terrain fetcher and chunk adapter

**Files:**
- Create: `highliner/etls/chunk/portugal/dtm_dgt.py`
- Create: `highliner/etls/chunk/portugal/main.py`
- Create: `highliner/etls/chunk/portugal/__init__.py`
- Create: `highliner/etls/chunk/portugal/__main__.py`
- Test: `tests/highliner/etls/chunk/portugal/test_dtm_dgt.py`
- Test: `tests/highliner/etls/chunk/portugal/test_main.py`

**Interfaces:**
- Produces: `fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]`, the multiprocessing-safe DTM fetcher.
- Produces: `REGIONS` containing the `mainland` Portugal region in EPSG:3763.

- [ ] Write failing tests for projected-country configuration, STAC item selection, credential validation, and cached-tile reuse.
- [ ] Run the selected tests and confirm they fail because Portugal modules are absent.
- [ ] Implement the DGT CDD authenticated STAC client and cache it under `cache/portugal/dgt_mdt_2m/`.
- [ ] Implement the standard country chunk CLI with the outward-rounded mainland bbox.
- [ ] Re-run the selected tests and confirm they pass.

### Task 2: Density and protected-area ETLs

**Files:**
- Create: `highliner/etls/density/portugal/{__init__,__main__,main}.py`
- Create: `highliner/etls/restriction/portugal/{__init__,__main__,main}.py`
- Modify: `highliner/core/restrictions.py`
- Modify: `highliner/core/density.py`
- Modify: `frontend/src/lib/i18n/restrictionStrings.ts`
- Test: `tests/highliner/etls/density/portugal/test_main.py`
- Test: `tests/highliner/etls/restriction/portugal/test_main.py`

**Interfaces:**
- Consumes: standard shared density/restriction builders.
- Produces: `pt_zpe`, `pt_zec`, and `pt_rnap` overlays with unique nonzero density bits.

- [ ] Write failing tests for the density country value, ICNF WFS pagination, output layer specs, and nonzero layer masks.
- [ ] Run the selected tests and confirm they fail because Portugal modules and layer definitions are absent.
- [ ] Implement the standard density CLI and ICNF WFS downloader using `BDG:zpe`, `BDG:sic`, and `BDG:rnap`.
- [ ] Add English backend and Catalan/Spanish frontend restriction copy, with each highlight a substring of its tooltip.
- [ ] Re-run the selected tests and confirm they pass.

### Task 3: Verify and document execution

**Files:**
- Modify: `docs/superpowers/plans/2026-08-01-portugal-etl.md`

- [ ] Run each Portugal CLI with `--help`.
- [ ] Run `just test` and `just check`.
- [ ] Commit the implementation, push `auto/39`, and open a PR linking `Fixes #39`.
- [ ] Add exact run commands and durable artifact paths to the PR description.
