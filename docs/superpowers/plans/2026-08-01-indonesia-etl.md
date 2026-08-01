# Indonesia ETL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Indonesia's terrain, density, and protected-area ETL adapters.

**Architecture:** Use BIG's public DEMNAS ImageServer to export each projected chunk as a 5 m GeoTIFF and convert sea-level pixels to the shared sea sentinel. Define Indonesian island regions in their matching UTM zones; download the national protected-forest layer through its public ArcGIS endpoint and store it as the country's overlay.

**Tech Stack:** Python 3.12, requests, rasterio, GeoPandas, pytest.

## Global Constraints

- DEMNAS is about 8 m, the finest nationally available public source; it is coarser than the preferred 5 m but below the 10 m cutoff.
- The fetch entry point must be module-level for multiprocessing pickling.
- Restriction metadata needs matching backend display text, Catalan/Spanish translations, and a non-zero unique density bit.

---

### Task 1: DEMNAS terrain client and chunk adapter

**Files:**
- Create: `highliner/etls/chunk/indonesia/dtm_demnas.py`
- Create: `highliner/etls/chunk/indonesia/main.py`
- Create: `highliner/etls/chunk/indonesia/__init__.py`
- Create: `highliner/etls/chunk/indonesia/__main__.py`
- Test: `tests/highliner/etls/chunk/indonesia/test_dtm_demnas.py`
- Test: `tests/highliner/etls/chunk/indonesia/test_main.py`

**Interfaces:**
- Produces: `fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]` and a `REGIONS` tuple passed to `shared.precompute`.

- [ ] Write tests for an ArcGIS export request, sea masking, invalid response rejection, and adapter source/CRS forwarding.
- [ ] Run the focused tests and verify they fail because the Indonesia modules do not exist.
- [ ] Implement the request/GeoTIFF validation, masking, module-level retry wrapper, and UTM island-region catalogue.
- [ ] Run the focused tests and verify they pass.

### Task 2: Country density and restrictions adapters

**Files:**
- Create: `highliner/etls/density/indonesia/{__init__,__main__,main}.py`
- Create: `highliner/etls/restriction/indonesia/{__init__,__main__,main}.py`
- Modify: `highliner/core/restrictions.py`
- Modify: `highliner/core/density.py`
- Modify: `frontend/src/lib/i18n/restrictionStrings.ts`
- Test: `tests/highliner/etls/density/indonesia/test_main.py`
- Test: `tests/highliner/etls/restriction/indonesia/test_main.py`

**Interfaces:**
- Produces: `python -m highliner.etls.density.indonesia` and `python -m highliner.etls.restriction.indonesia`.

- [ ] Write tests for country forwarding, protected-area pagination/loading, and a non-zero density bit.
- [ ] Run the focused tests and verify they fail because the Indonesia modules and layer metadata do not exist.
- [ ] Implement adapters around the shared writers, metadata, and translations.
- [ ] Run the focused tests and verify they pass.

### Task 3: Validate and publish

- [ ] Run each new CLI with `--help`, focused tests, `just test`, and `just check`.
- [ ] Commit the ETL implementation, push `auto/75`, and open a PR that closes #75 with exact run commands and durable artifact paths.
