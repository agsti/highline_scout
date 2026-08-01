# Denmark ETL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Denmark as a runnable chunk, density, and protected-area ETL country.

**Architecture:** Use Denmark's DHM/Terræn 0.4 m bare-earth product as cached, 10 km bulk GeoTIFF sheets in EPSG:25832. The chunk adapter selects the national extent; density reuses the generic country builder; restrictions download the official Danish Natura 2000 shapefile package and split its birds and habitats designations alongside a national protected-area layer.

**Tech Stack:** Python 3.12, requests, rasterio, GeoPandas, pytest.

## Global Constraints

- The country identifier is `denmark` and its projected CRS is `EPSG:25832`.
- The DTM fetcher must be a module-level `fetch(bbox, tiles_dir, cache_dir, crs)` function.
- Source tiles must be cached under `cache/denmark/` and the source nodata must become `-9999.0`.
- Every new restriction layer has display metadata, Catalan/Spanish text, and a non-zero density bit.

---

### Task 1: Danish DTM client and chunk adapter

**Files:**
- Create: `highliner/etls/chunk/denmark/{__init__,__main__,dtm_dhm,main}.py`
- Create: `tests/highliner/etls/chunk/denmark/test_main.py`

- [ ] Write failing tests for EPSG:25832 validation, projected national extent, cached-sheet reuse, and the module entry point.
- [ ] Implement a locked cached bulk-sheet client for DHM/Terræn and a Denmark region adapter.
- [ ] Run `uv run pytest tests/highliner/etls/chunk/denmark -v`.

### Task 2: Density and restriction adapters

**Files:**
- Create: `highliner/etls/density/denmark/{__init__,__main__,main}.py`
- Create: `highliner/etls/restriction/denmark/{__init__,__main__,main}.py`
- Create: `tests/highliner/etls/density/denmark/test_main.py`
- Create: `tests/highliner/etls/restriction/denmark/test_main.py`

- [ ] Write failing tests for the density country selection and Natura/directive splitting.
- [ ] Implement the three country packages and raw-file reuse.
- [ ] Run the three country test directories.

### Task 3: Restriction registry and verification

**Files:**
- Modify: `highliner/core/{restrictions,density}.py`
- Modify: `frontend/src/lib/i18n/restrictionStrings.ts`
- Modify: `highliner/etls/density/builder.py`
- Test: `tests/highliner/etls/density/test_restrictions.py`

- [ ] Write failing tests proving every Danish layer has a non-zero mask and density retains its highest bit.
- [ ] Add country-specific labels, translated strings, and widen density masks from signed 16-bit values.
- [ ] Run all Python and frontend checks plus all three `--help` commands.
