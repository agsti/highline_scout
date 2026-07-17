# Task 1 report: country ETL issue reconciliation

## Scope

- Added `scripts/sync_country_etl_issues.py`.
- Added `tests/test_sync_country_etl_issues.py`.
- No existing task files were changed.

## TDD evidence

### RED

Ran:

```text
uv run pytest tests/test_sync_country_etl_issues.py -q
```

Before implementation, collection failed with `FileNotFoundError` for
`scripts/sync_country_etl_issues.py`. This was the expected missing-feature
failure after adding parser and dry-run tests.

### GREEN

Ran:

```text
uv run pytest tests/test_sync_country_etl_issues.py -q
```

Result: `4 passed in 0.01s`.

Scoped static checks also passed:

```text
uv run ruff check scripts/sync_country_etl_issues.py tests/test_sync_country_etl_issues.py
uv run vulture scripts/sync_country_etl_issues.py --min-confidence 60
```

## Apply-mode concurrency follow-up

Apply-mode reconciliation now takes a local Linux advisory `fcntl.flock` lock
before listing GitHub issues and holds it until all missing issues are created.
This serializes concurrent local `--apply` processes, so the later process
refreshes its issue snapshot only after the earlier process has finished.
Dry runs do not acquire the lock and retain their read-only, nonblocking path.

The regression test replaces the lock, list, and create operations with local
fakes and asserts the exact ordering: lock acquisition, list, creation, then
lock release. It makes no GitHub calls. It was first run before the lock helper
existed and failed with the expected missing `_apply_lock` attribute.

Verification:

```text
uv run pytest tests/test_sync_country_etl_issues.py -q
.......                                                                  [100%]
7 passed in 0.01s

uv run ruff check scripts/sync_country_etl_issues.py tests/test_sync_country_etl_issues.py
All checks passed!

uv run mypy scripts/sync_country_etl_issues.py
Success: no issues found in 1 source file

uv run vulture scripts/sync_country_etl_issues.py --min-confidence 60
```

## Requirements covered

- `unfinished_countries()` accepts every non-`[X]` checklist marker.
- Dry run lists open `etl-country` issues and performs no create command.
- Apply mode skips existing exact titles and creates each missing `ETL: <country>`
  issue with the required label and five checkpoint body.
- `gh` failures return 1 and emit the command error to stderr.
- CLI supports `--countries-file` and `--apply`.

## Self-review

The implementation only reads the supplied Markdown and uses `gh issue list`
followed by `gh issue create` when explicitly requested. It never edits the
source file or changes existing issue state. Existing issue matching is exact by
title, as specified. One operational limit is the `gh issue list --limit 1000`
cap; it is ample for the current European backlog but would need pagination if
the labelled open-issue set grew beyond that.

## Review follow-up

- Checklist markers now accept any nonempty contents; only the exact uppercase
  marker `X` denotes a completed entry.
- Reconciliation preserves first-seen order while de-duplicating unfinished
  country entries, so apply mode can create a given country issue at most once.
- Added coverage for a multi-character marker and duplicate unfinished country
  entries.

Verification:

```text
uv run pytest tests/test_sync_country_etl_issues.py -q
.....                                                                    [100%]
5 passed in 0.01s

uv run ruff check scripts/sync_country_etl_issues.py tests/test_sync_country_etl_issues.py
All checks passed!
```

## Pagination follow-up

Replaced the bounded `gh issue list --limit 1000` lookup with `gh api graphql
--paginate --slurp`. The query is restricted to open `etl-country` issues and
requests GitHub's `pageInfo`, so the CLI fetches every page before reconciliation.
The JSON parser flattens all returned pages; a regression test supplies two
responses and verifies both existing titles are recognized.

Verification:

```text
uv run pytest tests/test_sync_country_etl_issues.py -q
......                                                                   [100%]
6 passed in 0.01s

uv run ruff check scripts/sync_country_etl_issues.py tests/test_sync_country_etl_issues.py
All checks passed!

uv run mypy scripts/sync_country_etl_issues.py
Success: no issues found in 1 source file

uv run vulture scripts/sync_country_etl_issues.py --min-confidence 60
```
