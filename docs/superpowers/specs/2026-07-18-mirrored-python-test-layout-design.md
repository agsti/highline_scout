# Mirrored Python Test Layout Design

## Goal

Reorganize the Python test suite so a test's path identifies the production
module it primarily verifies. Keep pytest behavior and all existing assertions
unchanged.

For example:

```text
highliner/etls/chunk/spain.py
tests/highliner/etls/chunk/test_spain.py
```

## Scope

This refactor covers the Python suite currently under `tests/`. Frontend Vitest
tests already live beside their components and libraries, and the Playwright
suite has its own conventional `frontend/e2e/` root; neither frontend suite
will move.

The refactor changes test locations and, where an existing test module covers
multiple production modules, divides or combines test modules. It does not
change product code, test behavior, test data, assertions, or fixture semantics.

## Layout and Naming

Production package paths are mirrored below the conventional plural `tests/`
root. Test modules use pytest's conventional `test_<module>.py` prefix:

```text
highliner/core/geo.py
tests/highliner/core/test_geo.py

highliner/server/repositories/chunked_store.py
tests/highliner/server/repositories/test_chunked_store.py

scripts/prefetch_ea_lidar.py
tests/scripts/test_prefetch_ea_lidar.py
```

Test directories will contain `__init__.py` files. This gives every mirrored
test module a unique import name even when several packages have a module with
the same leaf name, such as the chunk, density, and restriction `spain.py`
adapters. The root `tests/__init__.py` remains, preserving imports from
`tests.helpers`.

## Ownership Rules

Each test function belongs to the module whose public or internal behavior is
the subject of its assertions:

1. Tests of one production module move to its mirrored test module.
2. Existing aggregate files are split when their tests exercise independently
   owned modules. For example, route tests from `test_api.py` move to the
   corresponding router test modules, while app construction and middleware
   tests move to `tests/highliner/server/test_app.py`.
3. Existing files that separately test facets of one module are merged. The
   terrain extraction, sector, and slope tests become
   `tests/highliner/etls/chunk/test_terrain.py`.
4. A test may still use supporting models, serializers, or repositories without
   being duplicated under those modules. Ownership follows the behavior under
   assertion, not every import.
5. Tests that intentionally validate a flow spanning several production
   modules live under `tests/integration/`. This includes the synthetic full
   precompute-to-API pipeline and the fixture-backed API flow.
6. Repository-policy tests with no production Python module live under
   `tests/project/`. This includes validation of project-local country ETL
   skills.
7. Tests for executable support scripts mirror the `scripts/` tree below
   `tests/scripts/`.

Shared construction helpers remain in `tests/helpers.py`, and binary/static
test data remains under `tests/fixtures/`. Helpers used by only one mirrored
test module may remain local to that module.

## Collection and Compatibility

Moving tests must not change their import targets: tests continue importing the
installed `highliner` package rather than production files by relative path.
No compatibility forwarding modules remain at the old flat paths.

The refactor is complete when:

- `uv run pytest --collect-only -q` collects the same 286 cases as before;
- `just test` passes all 286 cases;
- `just check` passes, including strict mypy over the reorganized test tree;
- no `tests/test_*.py` modules remain at the root;
- every Python test module is either at a mirrored production path or in the
  documented `tests/integration/` or `tests/project/` exception area.

## Non-goals

- Rewriting tests to reduce mocking or change test granularity.
- Adding or deleting coverage.
- Renaming production modules.
- Moving frontend tests.
- Introducing pytest plugins or changing pytest import mode.
