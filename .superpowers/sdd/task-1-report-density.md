# Task 1: relocate the one-pass density candidate materializer

## TDD evidence

- RED: `uv run pytest tests/test_candidates.py -v` exited 2 during collection
  with `ModuleNotFoundError: No module named 'highliner.etl.density.candidates'`.
- GREEN: `uv run pytest tests/test_candidates.py tests/test_precompute.py -v`
  passed: 15 passed.
- Final verification: `uv run ruff check highliner/etl/density/candidates.py
  highliner/etl/chunk/candidates.py tests/test_candidates.py
  tests/test_precompute.py` passed; `uv run mypy
  highliner/etl/density/candidates.py highliner/etl/chunk/candidates.py` passed;
  the focused pytest command passed again with 15 passed; `git diff --check`
  passed.

## Changes

- Added `highliner.etl.density.candidates.load_candidates`, retaining the
  one-pass `read_pair_columns(path).to_candidates()` materialization.
- Deleted the former server-repository materializer.
- Updated the chunk writer documentation and all specified materializer test
  imports to the density package boundary.

## Self-review

- The materializer keeps its `str | Path` input and `list[Candidate]` output.
- Existing populated and empty parquet round-trip assertions pass unchanged.
- The implementation continues to rely on the columnar parser rather than
  duplicating parquet mapping logic.

## Concerns

- `highliner/etl/services/density.py` still imports the deleted server module.
  This is outside Task 1's explicit scoped files and is expected to be handled
  by the subsequent density-package relocation task.

## Review bridge fix

- Fixed `highliner/etl/services/density.py` to import `load_candidates` from
  `highliner.etl.density.candidates` instead of the deleted
  `highliner.server.repositories.candidates` module.
- RED command: `uv run pytest
  tests/test_cli.py::test_density_command_uses_region_directory -v` failed at
  collection with `ModuleNotFoundError: No module named
  'highliner.server.repositories.candidates'`.
- GREEN command: `uv run pytest
  tests/test_cli.py::test_density_command_uses_region_directory -v` passed:
  `1 passed in 0.64s`.
- Additional verification: `git diff --check` passed.

## Review bridge concerns

- This is intentionally an interim import bridge only; the density builder was
  not relocated.

## Re-review correction

- Sorted first-party imports in `highliner/etl/services/density.py` and narrowed
  its dependency comment: `load_candidates` is local to
  `highliner.etl.density`; only `chunked_store` remains server-side.
- `uv run ruff check highliner/etl/services/density.py` output:

  ```text
  All checks passed!
  ```

- `uv run pytest tests/test_cli.py::test_density_command_uses_region_directory -v`
  output:

  ```text
  ============================= test session starts ==============================
  platform linux -- Python 3.12.12, pytest-9.0.3, pluggy-1.6.0 -- /home/gus/projects/highliner_finder/.venv/bin/python
  cachedir: .pytest_cache
  rootdir: /home/gus/projects/highliner_finder
  configfile: pyproject.toml
  plugins: anyio-4.13.0
  collecting ... collected 1 item

  tests/test_cli.py::test_density_command_uses_region_directory PASSED     [100%]

  ============================== 1 passed in 0.63s ===============================
  ```
