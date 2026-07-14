# Density ETL Package Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place every density-specific offline calculation module under
`highliner.etl.density`, without changing the command interface or generated
density JSON.

**Architecture:** Split the existing density service into a local parquet
candidate reader and a local pyramid builder inside `highliner.etl.density`.
The command imports the local builder. Shared slippy-map tile math remains in
`highliner.core.tiles`, and shared region-grid reading remains in the server
repository because the `/density` endpoint and other server routes use them.

**Tech Stack:** Python 3.11+, pytest, pandas/pyarrow parquet, pyproj, Ruff,
mypy, Vulture.

## Global Constraints

- Preserve the console entry point `highliner-etl-density =
  "highliner.etl.density.main:main"`.
- Preserve `build_density(region_dir, zoom_levels, report) -> int` behavior and
  the `density/z{zoom}.json` row schema.
- Keep `highliner.core.tiles` in `core`; it is shared with the `/density`
  endpoint.
- Keep `chunked_store.read_grid` in the server repository; it is shared server
  region metadata reading.
- Remove density-only modules from `highliner.etl.services` and
  `highliner.server.repositories`.
- Match the repository's 88-column, lint-only Ruff style; do not add `noqa`
  directives for this refactor.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `highliner/etl/density/candidates.py` | Materialize a parquet pair partition as `Candidate` objects for one-pass offline aggregation. |
| `highliner/etl/density/builder.py` | Convert pair midpoints to tiles and write the density pyramid. |
| `highliner/etl/density/main.py` | Parse CLI arguments and invoke the local builder. |
| `highliner/etl/services/density.py` | Delete: superseded density builder location. |
| `highliner/server/repositories/candidates.py` | Delete: reader is only an offline density concern. |
| `highliner/etl/chunk/candidates.py` | Update its read-side module reference in the docstring. |
| `tests/test_candidates.py` | Exercise the relocated candidate materializer. |
| `tests/test_density.py` | Exercise the relocated density builder. |
| `tests/test_cli.py` | Monkeypatch the relocated CLI dependency. |
| `tests/test_precompute.py` | Read generated pair partitions through the relocated materializer. |

### Task 1: Relocate the one-pass density candidate materializer

**Files:**
- Create: `highliner/etl/density/candidates.py`
- Delete: `highliner/server/repositories/candidates.py`
- Modify: `highliner/etl/chunk/candidates.py:1-10`
- Modify: `tests/test_candidates.py:1-7`
- Modify: `tests/test_precompute.py:61,94,348-349`

**Interfaces:**
- Consumes: `highliner.server.repositories.partition_cache.read_pair_columns(path)`.
- Produces: `load_candidates(path: str | Path) -> list[Candidate]` from
  `highliner.etl.density.candidates`.
- Preserves: parquet data mapping and empty-partition behavior.

- [ ] **Step 1: Point materializer consumers at the intended density module**

  In `tests/test_candidates.py`, replace the import with:

  ```python
  from highliner.etl.density.candidates import load_candidates
  ```

  In `tests/test_precompute.py`, replace both local imports with the same
  density-package import. Do not alter their assertions: they prove generated
  pair partitions are still readable after the module move.

- [ ] **Step 2: Run the focused materializer tests to verify the import fails**

  Run:

  ```bash
  uv run pytest tests/test_candidates.py -v
  ```

  Expected: collection fails with `ModuleNotFoundError` for
  `highliner.etl.density.candidates`, proving the test targets the new package
  boundary rather than the removed server module.

- [ ] **Step 3: Create the density-local materializer**

  Create `highliner/etl/density/candidates.py` with the existing one-pass
  implementation, retaining the dependency on the columnar parser:

  ```python
  """Read precomputed pair partitions for offline density aggregation."""
  from pathlib import Path

  from highliner.models.candidate import Candidate
  from highliner.server.repositories.partition_cache import read_pair_columns


  def load_candidates(path: str | Path) -> list[Candidate]:
      """Materialize every pair in one partition for a single offline pass."""
      return read_pair_columns(path).to_candidates()
  ```

  Delete `highliner/server/repositories/candidates.py`. Update the write-side
  docstring in `highliner/etl/chunk/candidates.py` to name
  `highliner.etl.density.candidates` as the read-side location.

- [ ] **Step 4: Run focused tests to verify the relocated reader passes**

  Run:

  ```bash
  uv run pytest tests/test_candidates.py tests/test_precompute.py -v
  ```

  Expected: PASS. The round-trip and precompute tests confirm the local reader
  still handles populated and empty parquet files.

- [ ] **Step 5: Commit the independently working relocation**

  ```bash
  git add highliner/etl/density/candidates.py highliner/etl/chunk/candidates.py \
      highliner/server/repositories/candidates.py tests/test_candidates.py \
      tests/test_precompute.py
  git commit -m "refactor: move density candidate reader"
  ```

### Task 2: Move density pyramid construction beneath its command package

**Files:**
- Create: `highliner/etl/density/builder.py`
- Delete: `highliner/etl/services/density.py`
- Modify: `highliner/etl/density/main.py:1-30`
- Modify: `tests/test_density.py:1-8`
- Modify: `tests/test_cli.py:49-58`

**Interfaces:**
- Consumes: `load_candidates` from `highliner.etl.density.candidates`,
  `chunked_store.read_grid`, `core.geo.to_lonlat_crs`, and
  `core.tiles.lonlat_to_tile`.
- Produces: `build_density(region_dir: Path, zoom_levels: Iterable[int] =
  config.DENSITY_ZOOM_LEVELS, report: Callable[[int, int], None] | None = None)
  -> int` from `highliner.etl.density.builder`.
- Preserves: one density row per occupied `(z, x, y)` tile with `x`, `y`, `n`,
  `max_exp`, `min_len`, and `max_len` fields.

- [ ] **Step 1: Point builder tests and the CLI test at the intended module**

  In `tests/test_density.py`, replace:

  ```python
  from highliner.etl.services import density
  ```

  with:

  ```python
  from highliner.etl.density import builder
  ```

  Replace each `density.build_density(...)` call with
  `builder.build_density(...)`. In `tests/test_cli.py`, change the monkeypatch
  target to:

  ```python
  "highliner.etl.density.main.builder.build_density"
  ```

- [ ] **Step 2: Run the focused builder test to verify the new module fails to import**

  Run:

  ```bash
  uv run pytest tests/test_density.py::test_two_pairs_share_a_cell_third_apart -v
  ```

  Expected: collection fails with an import error for
  `highliner.etl.density.builder`, proving the existing aggregation test now
  specifies the new public module location.

- [ ] **Step 3: Create the local builder and connect the command**

  Move the full `build_density` and `_midpoint_lonlat` implementations from
  `highliner/etl/services/density.py` into
  `highliner/etl/density/builder.py`. Update its imports so the reader is
  local:

  ```python
  from highliner.etl.density.candidates import load_candidates
  ```

  Keep these shared imports unchanged in purpose:

  ```python
  from highliner.core import config, geo, tiles
  from highliner.server.repositories import chunked_store
  ```

  In `highliner/etl/density/main.py`, replace the service import with:

  ```python
  from highliner.etl.density import builder
  ```

  and call `builder.build_density(rdir, report=report)`. Delete
  `highliner/etl/services/density.py`.

- [ ] **Step 4: Run focused aggregation and CLI tests**

  Run:

  ```bash
  uv run pytest tests/test_density.py tests/test_cli.py -v
  ```

  Expected: PASS. This confirms the candidate midpoint aggregation, default
  zoom output, progress callback, and CLI region-directory handoff retain their
  previous behavior.

- [ ] **Step 5: Commit the working builder relocation**

  ```bash
  git add highliner/etl/density/builder.py highliner/etl/density/main.py \
      highliner/etl/services/density.py tests/test_density.py tests/test_cli.py
  git commit -m "refactor: colocate density builder with command"
  ```

### Task 3: Prove the old density-specific package locations are gone

**Files:**
- Modify: documentation only if a current (non-historical) reference to either
  removed module remains.
- Verify: `highliner/`, `tests/`, `pyproject.toml`

**Interfaces:**
- Consumes: the completed package relocations from Tasks 1 and 2.
- Produces: no imports of the deleted density-only modules; unchanged shared
  `core.tiles` and `chunked_store.read_grid` locations.

- [ ] **Step 1: Search for stale imports and references**

  Run:

  ```bash
  rg -n 'highliner\.etl\.services\.density|highliner\.server\.repositories\.candidates' \
      highliner tests pyproject.toml
  ```

  Expected: no matches. Do not alter historical design or implementation-plan
  documents: they intentionally record the code layout that existed when they
  were written.

- [ ] **Step 2: Run repository quality checks**

  Run:

  ```bash
  just check
  just test
  ```

  Expected: both commands exit 0. `just check` validates Ruff, file length,
  strict mypy, and Vulture; `just test` validates all Python behavior.

- [ ] **Step 3: Inspect the final diff**

  Run:

  ```bash
  git diff --check
  git status --short
  ```

  Expected: no whitespace errors. The two relocation commits are the complete
  implementation; do not create an empty verification commit.
