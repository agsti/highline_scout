# Belgium ETL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add chunk, density, and restriction ETL entry points for Belgium.

**Architecture:** Two Lambert 72 precompute regions select their native,
public bare-earth products through module-level fetchers. The density adapter is
country-only; the restriction adapter writes the existing EU Birds and Habitats
overlays from Belgium's public register.

**Tech Stack:** Python 3.12, rasterio, requests, GeoPandas, pytest.

## Global Constraints

- Fetchers expose `fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]` at module scope.
- Terrain resolution is resampled to the pipeline's 5 m analysis grid.
- Region bboxes use EPSG:31370 metres and are rounded outward to 1 km.
- Durable outputs remain scoped below `data/belgium/` and `cache/belgium/`.

---

### Task 1: Flemish terrain client and chunk configuration

**Files:** Create `highliner/etls/chunk/belgium/dtm_dhmv.py`,
`highliner/etls/chunk/belgium/main.py`, package entry points, and focused
tests under `tests/highliner/etls/chunk/belgium/`.

- [ ] Write failing tests for a Lambert 72 request, multipart TIFF extraction,
  and source no-data handling.
- [ ] Implement the module-level DHMV WCS fetcher and the Flanders region.
- [ ] Run the Belgium chunk tests.

### Task 2: Walloon terrain client and remaining region

**Files:** Create `highliner/etls/chunk/belgium/dtm_wallonie.py` and extend
the chunk tests.

- [ ] Write failing tests for cached province downloads and bbox selection.
- [ ] Implement the cached Wallonia bulk-sheet fetcher and Wallonia region.
- [ ] Run the Belgium chunk tests.

### Task 3: Density and restriction adapters

**Files:** Create country packages beneath `highliner/etls/density/belgium/`
and `highliner/etls/restriction/belgium/`, plus their tests.

- [ ] Write failing tests for all three CLI modules and Birds/Habitats split.
- [ ] Implement country adapters and the public-register downloader.
- [ ] Run the country adapter tests.

### Task 4: Verification and delivery

- [ ] Run `uv run python -m highliner.etls.chunk.belgium --help`, density and
  restriction help commands.
- [ ] Run `just test` and `just check`.
- [ ] Commit, push `auto/11`, and open a PR closing #11 with exact run and
  artifact sections.
