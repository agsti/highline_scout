# Chunk ETL Module Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `highliner.etl.chunk` own every module used exclusively by the chunk-precompute command, without changing its CLI or precompute output.

**Architecture:** The chunk package becomes the complete write-side terrain pipeline: DTM acquisition, terrain characterization, pairing, parquet writers, and orchestration live beside its command entry point. The remaining generic ETL packages retain only the density service and restrictions repository; shared models, core helpers, and server read-side modules remain in place.

**Tech Stack:** Python 3.12, NumPy/SciPy, Rasterio, GeoPandas/Pandas, Pytest, Ruff, mypy, Vulture.

## Global Constraints

- Preserve the console script target `highliner.etl.chunk.main:main` and all command-line arguments.
- Preserve behavior, signatures, parquet schemas, partition names, and chunk ownership semantics; this is a package-boundary refactor only.
- Delete old chunk-only import paths rather than leaving compatibility re-exports.
- Keep density at `highliner.etl.services.density` and restrictions at `highliner.etl.repositories.restrictions`.
- Maintain repository checks: Ruff at 88 columns, strict mypy, Vulture, 500-line file cap, and Pytest.

---

## File structure

| Path | Responsibility after refactor |
| --- | --- |
| `highliner/etl/chunk/main.py` | Unchanged CLI entry point; imports package-local precompute orchestration. |
| `highliner/etl/chunk/precompute.py` | Region grid creation, chunk processing, atomic partition writes, and worker pool. |
| `highliner/etl/chunk/dtm.py` | ICGC/IDEE/CNIG DTM retrieval and raster merging. |
| `highliner/etl/chunk/terrain.py` | Anchor extraction from DTM rasters. |
| `highliner/etl/chunk/pairing.py` | Candidate pairing and exposure calculations. |
| `highliner/etl/chunk/anchors.py` | Anchor parquet write side. |
| `highliner/etl/chunk/candidates.py` | Candidate parquet write side. |
| `highliner/etl/services/density.py` | Remains the standalone density ETL service. |
| `highliner/etl/repositories/restrictions.py` | Remains the standalone restrictions ETL repository. |

### Task 1: Move chunk-local parquet writers and update their consumers

**Files:**
- Create: `highliner/etl/chunk/anchors.py` (moved from `highliner/etl/repositories/anchors.py`)
- Create: `highliner/etl/chunk/candidates.py` (moved from `highliner/etl/repositories/candidates.py`)
- Modify: `tests/test_anchors.py`, `tests/test_candidates.py`, `tests/test_api.py`, `tests/test_chunked_store.py`, `tests/test_partition_cache.py`, `tests/test_density.py`
- Modify: `highliner/server/repositories/candidates.py`, `highliner/server/repositories/partition_cache.py`
- Delete: `highliner/etl/repositories/anchors.py`, `highliner/etl/repositories/candidates.py`

**Interfaces:**
- Consumes: `Anchor` and `Candidate` domain dataclasses from `highliner.models`.
- Produces: `save_anchors(anchors: list[Anchor], path: str | Path) -> None` and `save_candidates(candidates: list[Candidate], path: str | Path) -> None` at `highliner.etl.chunk` paths.

- [ ] **Step 1: Write the failing import migration in writer consumers**

Replace each writer import with:

```python
from highliner.etl.chunk.anchors import save_anchors
from highliner.etl.chunk.candidates import save_candidates
```

Do not modify fixture data or assertions; the existing tests remain the behavioral specification.

- [ ] **Step 2: Run the affected test collection to verify it fails**

Run: `uv run pytest tests/test_anchors.py tests/test_candidates.py tests/test_api.py tests/test_chunked_store.py tests/test_partition_cache.py tests/test_density.py -q`

Expected: collection errors because the two package-local modules do not exist yet.

- [ ] **Step 3: Move the writer modules and correct provenance documentation**

Use `git mv` for both modules. Retain exactly these public signatures:

```python
def save_anchors(anchors: list[Anchor], path: str | Path) -> None: ...
def save_candidates(candidates: list[Candidate], path: str | Path) -> None: ...
```

Update the docstrings in the two server read-side modules to refer to
`highliner.etl.chunk.{anchors,candidates}`, not the deleted writer paths.

- [ ] **Step 4: Run the affected tests to verify it passes**

Run: `uv run pytest tests/test_anchors.py tests/test_candidates.py tests/test_api.py tests/test_chunked_store.py tests/test_partition_cache.py tests/test_density.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add highliner/etl/chunk/anchors.py highliner/etl/chunk/candidates.py highliner/etl/repositories/anchors.py highliner/etl/repositories/candidates.py highliner/server/repositories/candidates.py highliner/server/repositories/partition_cache.py tests/test_anchors.py tests/test_candidates.py tests/test_api.py tests/test_chunked_store.py tests/test_partition_cache.py tests/test_density.py
git commit -m "refactor: colocate chunk parquet writers"
```

### Task 2: Move DTM, terrain, and pairing implementation into the chunk package

**Files:**
- Create: `highliner/etl/chunk/dtm.py` (moved from `highliner/etl/repositories/dtm.py`)
- Create: `highliner/etl/chunk/terrain.py` (moved from `highliner/etl/services/terrain.py`)
- Create: `highliner/etl/chunk/pairing.py` (moved from `highliner/etl/services/pairing.py`)
- Modify: `tests/test_ingest.py`, `tests/test_terrain_extract.py`, `tests/test_terrain_sectors.py`, `tests/test_terrain_slope.py`, `tests/test_pairing.py`, `tests/test_characterization.py`, `tests/test_integration.py`
- Delete: `highliner/etl/repositories/dtm.py`, `highliner/etl/services/terrain.py`, `highliner/etl/services/pairing.py`

**Interfaces:**
- Consumes: shared `Raster`, `Anchor`, `Candidate`, config, and geographic helpers.
- Produces: unchanged `fetch_tiles(...)`, `raster_from_tiles(...)`, `extract_anchors(...)`, and `find_candidates(...)` at `highliner.etl.chunk` paths.

- [ ] **Step 1: Write the failing import migration in algorithm tests**

Use package-local imports:

```python
from highliner.etl.chunk import pairing, terrain
from highliner.etl.chunk.dtm import fetch_tiles
from highliner.etl.chunk.pairing import find_candidates
from highliner.etl.chunk.terrain import extract_anchors
```

Replace every `monkeypatch.setattr` string rooted at
`highliner.etl.repositories.dtm` with `highliner.etl.chunk.dtm`; keep its
patched attribute unchanged.

- [ ] **Step 2: Run the algorithm tests to verify they fail**

Run: `uv run pytest tests/test_ingest.py tests/test_terrain_extract.py tests/test_terrain_sectors.py tests/test_terrain_slope.py tests/test_pairing.py tests/test_characterization.py tests/test_integration.py -q`

Expected: collection/import failures for the missing package-local modules.

- [ ] **Step 3: Move the three modules without algorithm changes**

Use `git mv` to relocate the DTM adapter, anchor extraction module, and candidate pairing module. Do not change network retries, raster sampling, sector checks, or exposure logic.

- [ ] **Step 4: Run the algorithm tests to verify they pass**

Run: `uv run pytest tests/test_ingest.py tests/test_terrain_extract.py tests/test_terrain_sectors.py tests/test_terrain_slope.py tests/test_pairing.py tests/test_characterization.py tests/test_integration.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add highliner/etl/chunk/dtm.py highliner/etl/chunk/terrain.py highliner/etl/chunk/pairing.py highliner/etl/repositories/dtm.py highliner/etl/services/terrain.py highliner/etl/services/pairing.py tests/test_ingest.py tests/test_terrain_extract.py tests/test_terrain_sectors.py tests/test_terrain_slope.py tests/test_pairing.py tests/test_characterization.py tests/test_integration.py
git commit -m "refactor: colocate chunk terrain pipeline"
```

### Task 3: Move precompute orchestration, rewire the command, and document the final boundary

**Files:**
- Create: `highliner/etl/chunk/precompute.py` (moved from `highliner/etl/services/precompute.py`)
- Modify: `highliner/etl/chunk/main.py`, `tests/test_cli.py`, `tests/test_precompute.py`, `tests/test_integration.py`, `AGENTS.md`
- Delete: `highliner/etl/services/precompute.py`

**Interfaces:**
- Consumes: `highliner.etl.chunk.dtm`, `.anchors.save_anchors`, `.candidates.save_candidates`, `.terrain.extract_anchors`, and `.pairing.find_candidates`.
- Produces: unchanged `chunk_grid(...)`, `process_chunk(...) -> int`, and `precompute(...) -> int`, imported by main as `precompute_service`.

- [ ] **Step 1: Write the failing orchestration import migration**

Use the package-local module in direct imports and monkeypatch paths:

```python
from highliner.etl.chunk import precompute
monkeypatch.setattr("highliner.etl.chunk.precompute.precompute", fake)
```

Update DTM imports and monkeypatch strings in `tests/test_precompute.py` to
`highliner.etl.chunk.dtm`. Keep all density imports in `tests/test_cli.py` and
`tests/test_density.py` at their current paths.

- [ ] **Step 2: Run precompute and CLI tests to verify they fail**

Run: `uv run pytest tests/test_precompute.py tests/test_cli.py tests/test_integration.py -q`

Expected: import failures for `highliner.etl.chunk.precompute`.

- [ ] **Step 3: Move orchestration and replace its imports**

Move `highliner/etl/services/precompute.py` to `highliner/etl/chunk/precompute.py`. Its imports must become:

```python
from highliner.etl.chunk import dtm
from highliner.etl.chunk.anchors import save_anchors
from highliner.etl.chunk.candidates import save_candidates
from highliner.etl.chunk.pairing import find_candidates
from highliner.etl.chunk.terrain import extract_anchors
```

In `highliner/etl/chunk/main.py`, replace the service import with:

```python
from highliner.etl.chunk import precompute as precompute_service
```

Keep `highliner/etl/services/__init__.py` and `highliner/etl/repositories/__init__.py`: their density and restrictions modules still use those packages.

- [ ] **Step 4: Update ownership documentation and remove stale references**

In `AGENTS.md`, describe `etl/chunk/` as the complete chunk-precompute pipeline and change all chunk implementation paths from `etl/services/*` or `etl/repositories/*` to `etl/chunk/*`. Retain density and restrictions paths unchanged. Update writer provenance docstrings as needed.

Run: `rg -n "etl\\.(services|repositories)\\.(precompute|terrain|pairing|dtm|anchors|candidates)" AGENTS.md highliner tests`

Expected: no output with exit status 1.

- [ ] **Step 5: Run targeted tests to verify behavior and the CLI entry point**

Run: `uv run pytest tests/test_precompute.py tests/test_cli.py tests/test_integration.py -q`

Expected: PASS.

Run: `uv run pytest tests/test_cli.py::test_chunk_entry_point_declared -q`

Expected: PASS, confirming `highliner-etl-chunk = "highliner.etl.chunk.main:main"` is unchanged.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md highliner/etl/chunk/precompute.py highliner/etl/chunk/main.py highliner/etl/services/precompute.py tests/test_precompute.py tests/test_cli.py tests/test_integration.py
git commit -m "refactor: make chunk ETL self-contained"
```

### Task 4: Run repository-wide verification

**Files:** Verify only; do not modify files unless a check identifies a refactor defect.

**Interfaces:** Consumes the completed package relocation and produces verification evidence for CLI import paths, backend behavior, linting, types, dead-code analysis, and file-size limits.

- [ ] **Step 1: Run the full backend suite**

Run: `just test`

Expected: PASS.

- [ ] **Step 2: Run all repository static checks**

Run: `just check`

Expected: Ruff, strict mypy, Vulture, and the file-length cap pass.

- [ ] **Step 3: Confirm final ownership paths**

Run: `rg --files highliner/etl/services highliner/etl/repositories highliner/etl/chunk | sort`

Expected: `density.py` remains under `services`, `restrictions.py` remains under `repositories`, and the six relocated modules plus `main.py` are under `chunk`.

- [ ] **Step 4: Commit check-driven corrections separately, if needed**

If verification required a correction, stage only the affected source and test files and commit with a `fix:` subject naming the concrete issue. If all checks pass without changes, do not create an empty commit.

## Plan self-review

- Spec coverage: Tasks 1-3 move all six chunk-only modules, preserve the CLI, retain density/restrictions and shared code, update tests, and document ownership. Task 4 validates the full result.
- Placeholder scan: no deferred work or unspecified implementation remains.
- Type consistency: all listed interfaces retain their current signatures; Task 3 imports only files created in Tasks 1-2.
