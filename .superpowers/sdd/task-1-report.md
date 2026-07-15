# Task 1 report: country-neutral ETLs

## Delivered

- Moved the ETL package from `highliner.etl` to `highliner.etls`, including
  chunk, density, restrictions, entry-point, and supporting modules.
- Renamed chunk precompute to `highliner.etls.chunk.shared` and exposed the
  country-explicit `precompute()` and `region_output_dir()` interfaces.
- Made output and CNIG cache paths use the passed country rather than a region
  lookup; the chunk CLI obtains its legacy defaults then passes them explicitly.
- Made density require `grid.json` and read its CRS from that precomputed
  metadata, eliminating the region-default fallback.
- Updated production references, entry points, documentation strings, and tests
  to use `highliner.etls`.

## TDD evidence

1. Added `test_precompute_uses_explicit_country_for_outputs_and_cache`.
2. Verified it failed before the package existed:
   `ModuleNotFoundError: No module named 'highliner.etls'`.
3. Implemented the move and explicit interface.
4. Verified the target test passed, then the focused migration suite passed.

## Verification

- `uv run pytest tests/test_precompute.py tests/test_ingest.py tests/test_density.py tests/test_candidates.py tests/test_anchors.py tests/test_partition_cache.py -v`
  — 49 passed.
- Remaining moved-import tests including characterization, terrain, CLI, and
  integration — 24 passed.
- `uv run pytest -v` — 210 passed (three existing dependency/runtime warnings).
- `just check` passed ruff, file-length, mypy, and vulture. Its final frontend
  `npm test` step could not run because `npm` is unavailable in this environment.
