# Task 3 report: self-contained chunk orchestration

## Scope

Moved chunk-precompute orchestration from `highliner.etl.services.precompute`
to `highliner.etl.chunk.precompute`. The chunk CLI, imports, monkeypatch paths,
and architecture guide now use the package-local module. The density and
restrictions packages remain in their existing `services` and `repositories`
namespaces.

## Test-first evidence

Updated the precompute and integration imports plus the CLI monkeypatch target
to `highliner.etl.chunk.precompute` before creating that module. The focused
suite then failed during collection with the expected missing-package-local
import error. After the move, it passed.

The requested focused CLI entry-point test did not exist in the current suite,
so it was added by separating that assertion from the broader command-script
test.

## Verification

- `rg -n "etl\\.(services|repositories)\\.(precompute|terrain|pairing|dtm|anchors|candidates)" AGENTS.md highliner tests` exited 1 with no matches.
- `uv run pytest tests/test_precompute.py tests/test_cli.py tests/test_integration.py -q` — 20 passed.
- `uv run pytest tests/test_cli.py::test_chunk_entry_point_declared -q` — 1 passed.
- `just test` — 164 passed (one existing Starlette/httpx deprecation warning).
