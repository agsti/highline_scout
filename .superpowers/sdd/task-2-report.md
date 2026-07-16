# Task 2 report: country-derived density restrictions

## Scope

- `highliner/etls/density/builder.py`
- `highliner/core/density.py`
- `tests/test_density.py`

`build_density()` now defaults its restrictions directory to the parent country
of `region_dir`. Explicit `restrictions_dir` arguments remain authoritative.

## TDD evidence

### Red

Added `test_builder_defaults_to_its_region_country_restrictions`, which creates
an Italy-parent region and an adjacent `zps.parquet` restriction. Before the
implementation, this command failed as expected:

```
uv run pytest tests/test_density.py::test_builder_defaults_to_its_region_country_restrictions -v
FAILED ... assert np.int8(7) == 8
1 failed
```

The pre-change builder read the repository's Spain restriction directory,
producing the Spain mask (`7`) rather than the Italian `zps` mask (`8`).

After replacing the fallback, the same test still failed with mask `0`.
Root-cause inspection found that `highliner/core/density.py` omitted the
already-registered Italian IDs from `LAYER_BITS`. The task owner authorized the
minimal scope expansion to add `zps`, `zsc`, and `euap` as bits 8, 16, and 32.

### Green

```
uv run pytest tests/test_density.py::test_builder_defaults_to_its_region_country_restrictions -v
1 passed

uv run pytest tests/test_density.py -v
10 passed, 2 warnings in 2.42s
```

The two warnings are the existing multiprocessing `fork()` deprecation warning
from the parallel-worker coverage; there were no test failures.

## Files changed

- `highliner/etls/density/builder.py` — derive standalone restriction input
  from `region_dir.parent / "restrictions"`.
- `highliner/core/density.py` — assign the existing Italian layer IDs their
  next registry-order mask bits: 8, 16, and 32.
- `tests/test_density.py` — regression coverage for the Italy-parent default.

## Self-review

- The explicit `restrictions_dir` parameter is unchanged and still takes
  precedence via `or`.
- `build_country_density` was not changed.
- The NPZ mask field remains the existing integer representation; only new bit
  values were registered.
- No unrelated user changes are included in the intended commit.

## Concerns

None. The test suite reports only the known multiprocessing fork deprecation
warnings.

## Review fix: deterministic former-default fixture

### Scope

Addressed the review finding in
`test_builder_defaults_to_its_region_country_restrictions` only. The test now
creates the historical default directory under its own `tmp_path`:
`<DATA_DIR>/spain/restrictions/{zepa,zec,enp}.parquet`. It patches
`config.DATA_DIR` to that temporary root, alongside its Italy `zps.parquet`
fixture.

This makes the old fallback deterministic: it reads the overlapping Spain
fixtures and produces mask `7`; the country-derived fallback reads only Italy
`zps` and produces mask `8`.

### TDD evidence

After adding the Spain fixture and temporary configuration, I temporarily
restored the former `config.DATA_DIR / config.DEFAULT_COUNTRY / "restrictions"`
fallback and ran:

```
uv run pytest tests/test_density.py::test_builder_defaults_to_its_region_country_restrictions -v
FAILED ... assert np.int8(7) == 8
1 failed
```

That failure proves the regression no longer depends on ambient repository
`data/spain` state. Restoring the country-derived fallback made the same test
pass.

### Verification

```
uv run pytest tests/test_density.py::test_builder_defaults_to_its_region_country_restrictions -v
1 passed in 1.39s

uv run pytest tests/test_density.py -v
10 passed, 2 warnings in 1.96s
```

The two warnings are the known multiprocessing `fork()` deprecation warnings
from `test_parallel_density_matches_single_worker_output`.

### Self-review

- The temporary Spain fixture exactly models the previous fallback path by
  patching `config.DATA_DIR`; no repository data participates.
- Spain's combined bits (`7`) differ from Italy's `zps` bit (`8`), so the
  assertion distinguishes the former default from the intended country path.
- The production fallback and all unrelated Task 2 changes remain untouched.

### Concerns

None.
