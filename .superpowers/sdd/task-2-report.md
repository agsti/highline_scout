# Task 2 report: colocate chunk terrain pipeline

## Scope

- Moved the unchanged DTM adapter to `highliner/etl/chunk/dtm.py`.
- Moved the unchanged terrain extraction implementation to
  `highliner/etl/chunk/terrain.py`.
- Moved the unchanged candidate pairing implementation to
  `highliner/etl/chunk/pairing.py`.
- Migrated direct algorithm-test imports and DTM monkeypatch targets to the
  chunk package, including `tests/test_precompute.py` discovered by the full
  suite.
- Updated the three imports in `highliner/etl/services/precompute.py` so the
  existing orchestration continues to consume the relocated modules. This was
  an explicitly approved necessary consumer migration; no orchestration logic
  changed.

## TDD evidence

### RED

After changing the algorithm tests to use the package-local imports, before
moving production modules, I ran:

```text
uv run pytest tests/test_ingest.py tests/test_terrain_extract.py tests/test_terrain_sectors.py tests/test_terrain_slope.py tests/test_pairing.py tests/test_characterization.py tests/test_integration.py -q
6 collection errors, exit 2
```

The expected failures were missing package-local module imports:

```text
ImportError: cannot import name 'dtm' from 'highliner.etl.chunk'
ModuleNotFoundError: No module named 'highliner.etl.chunk.pairing'
```

### GREEN

I used `git mv` for the three modules and updated the three `precompute.py`
consumer imports. The first focused green run found one remaining local legacy
import inside `test_batch_blocking_does_not_change_results`; I migrated it.
The focused suite then passed:

```text
37 passed, 1 warning in 0.93s
```

The first full-suite run then exposed nine stale direct DTM imports in
`tests/test_precompute.py`. I migrated only those test imports and its sleep
monkeypatch string. The final full verification passed:

```text
just test
163 passed, 1 warning in 10.03s
```

The warning is the existing FastAPI/Starlette `TestClient` deprecation.

## Self-review

- `git diff --check` completed with exit 0.
- A repository search found no remaining imports rooted at
  `highliner.etl.repositories.dtm`, `highliner.etl.services.terrain`, or
  `highliner.etl.services.pairing`.
- The moved modules have no algorithm edits; the only production modification
  beyond their relocation is the necessary three-line consumer import update
  in `precompute.py`.
- Unrelated working-tree changes (frontend, documentation, Task 1 report, and
  other untracked work) were not staged or modified by this task.

## Commit

`refactor: colocate chunk terrain pipeline` (created after this report is
staged with the Task 2 files only).

## Concerns

None.
