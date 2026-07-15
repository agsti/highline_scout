# Task 2 report: Spain chunk ETL adapter

## Scope

- Added `highliner.etls.chunk.spain`, the Spain-specific chunk precompute
  adapter with an explicit `COUNTRY`, immutable `Region` catalogue, per-region
  CRS/source configuration, serial and concurrent execution, and `python -m`
  support.
- Replaced the generic chunk console target with
  `highliner.etls.chunk.spain:main`.
- Removed the legacy generic chunk CLI and subprocess-oriented Spain wrapper.
- Replaced the subprocess test with a direct adapter contract test and updated
  the console entry-point assertion.

## TDD evidence

### RED

After replacing the legacy Spain-wrapper test with the direct adapter test, I
ran:

```text
uv run pytest tests/test_precompute_spain.py::test_spain_chunk_adapter_forwards_country_and_region -v
```

It failed at collection because `highliner.etls.chunk.spain` did not exist.

### GREEN

After adding the adapter, the focused test passed. The requested test set then
passed:

```text
uv run pytest tests/test_precompute_spain.py tests/test_cli.py -v
10 passed in 0.64s
```

## Verification

- `git diff --check` passed.
- Ruff, file-length validation, mypy, and vulture passed through `just check`.
- The final frontend test step of `just check` could not run because `npm` is
  not installed in this environment (`sh: 1: npm: not found`).

## Commit

`feat: add Spain chunk ETL adapter`

## Concerns

`catalonia2` remains in the inherited Spain catalogue and is configured for
ICGC/EPSG:25831. The task brief did not provide a replacement full-Catalonia
bbox; no new geographic extent was invented.

## Follow-up: reviewer configuration gap

- Added explicit `catalonia` and `catalunya` catalogue entries, both with the
  inherited Catalonia sample bbox, `EPSG:25831`, and the `icgc` source.
- Added parameterized direct-adapter coverage proving each alias is selected
  and forwards those exact CRS/source values to shared precompute.
- Verification: `uv run pytest tests/test_precompute_spain.py tests/test_cli.py
  -v` passed with 12 tests.
