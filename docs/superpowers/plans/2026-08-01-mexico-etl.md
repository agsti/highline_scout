# Mexico ETL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Mexico to the terrain precompute, density, and restriction ETLs.

**Architecture:** The chunk adapter will use INEGI's public 5 m terrain-sheet catalogue and cache downloaded ASCII archives per sheet. Mexico is divided into five UTM-zone regions to keep terrain calculations metric. The restrictions adapter consumes CONANP's protected-natural-area service and emits one Mexico-specific overlay.

**Tech Stack:** Python 3.12, requests, rasterio, pyproj, GeoPandas, pytest.

## Global Constraints

- The DTM fetcher is module-level and has `fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]`.
- Use INEGI 5 m terrain, never the surface model or the 15 m CEM.
- Keep durable DTM downloads under `cache/mexico/`; ETL outputs remain under `data/mexico/`.
- Add each new restriction layer to backend metadata, all UI translations, and `LAYER_BITS`.

---

### Task 1: INEGI terrain-sheet client and Mexico chunk adapter

**Files:**
- Create: `highliner/etls/chunk/mexico/{__init__.py,__main__.py,main.py,dtm_inegi.py}`
- Create: `tests/highliner/etls/chunk/mexico/{__init__.py,test_main.py,test_dtm_inegi.py}`

- [ ] Write failing tests for the public sheet-catalogue request, sheet selection, archive reuse, and `--only` chunk forwarding.
- [ ] Run the focused tests and confirm import/module failures.
- [ ] Implement the cached INEGI terrain fetcher and five UTM-zone region catalogue.
- [ ] Run focused tests and confirm passing results.

### Task 2: Country command adapters and restrictions

**Files:**
- Create: `highliner/etls/density/mexico/{__init__.py,__main__.py,main.py}`
- Create: `highliner/etls/restriction/mexico/{__init__.py,__main__.py,main.py}`
- Modify: `highliner/core/restrictions.py`, `highliner/core/density.py`, `frontend/src/lib/i18n/restrictionStrings.ts`
- Create: `tests/highliner/etls/density/mexico/{__init__.py,test_main.py}`
- Create: `tests/highliner/etls/restriction/mexico/{__init__.py,test_main.py}`

- [ ] Write failing tests for adapter dispatch and layer-mask registration.
- [ ] Run focused tests and confirm missing-package failures.
- [ ] Implement adapters, CONANP download/load path, layer metadata, and translations.
- [ ] Run focused tests and confirm passing results.

### Task 3: Verify and document operation

**Files:**
- Modify: `docs/superpowers/plans/2026-08-01-mexico-etl.md`

- [ ] Run all three help commands, `just test`, and `just check`.
- [ ] Run one real small chunk and verify temporary tiles are removed and parquet output exists.
- [ ] Commit the completed implementation and open a PR with exact run and artifact paths.
