# Country ETL Issue Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track country-ETL implementation in GitHub issues and reconcile unfinished country entries into issues.

**Architecture:** A Python CLI parses unfinished checklist entries, lists open `etl-country` issues through `gh`, and creates only missing issues when explicitly applied. The two skills use only issues and labels for coordination.

**Tech Stack:** Python 3.11 standard library, `gh` CLI, pytest, Markdown skill files.

## Global Constraints

- Dry run is the default; `--apply` is required to create an issue.
- `[X]` is done; every other checklist marker is unfinished.
- The utility never edits the source Markdown, closes issues, changes labels, or duplicates an open issue.
- The skills mention only GitHub issues and labels, never backlog files or the reconciliation utility.
- Agents report each checkpoint and at least every 30 minutes of active implementation.

---

### Task 1: Add the reconciliation utility

**Files:**

- Create: `scripts/sync_country_etl_issues.py`
- Test: `tests/test_sync_country_etl_issues.py`

**Interfaces:** `unfinished_countries(markdown: str) -> list[str]` and `main(argv: list[str] | None = None) -> int`.

- [ ] Write failing parser and dry-run tests: an input containing `[ ] Albania`, `[X] Spain`, and `[P] France` returns Albania and France; dry run calls only `gh issue list` and prints `would create: ETL: Albania`.
- [ ] Run `uv run pytest tests/test_sync_country_etl_issues.py -q`; confirm it fails because the script is missing.
- [ ] Implement `argparse` options `--countries-file` (default `Path("COUNTRIES.md")`) and `--apply`; use a multiline checklist regex, `subprocess.run` for `gh`, `ETL: <country>` issue titles, and an `etl-country` label. Apply mode creates only missing titles and the issue body has all five approved checkpoints. A `CalledProcessError` prints to stderr and returns 1.
- [ ] Add tests for apply mode skipping an already-listed `ETL: France` issue and for `gh` failure.
- [ ] Run `uv run pytest tests/test_sync_country_etl_issues.py -q`; confirm it passes; commit `feat: sync country ETL issues`.

### Task 2: Replace the two coordination skills

**Files:**

- Modify: `.claude/skills/adding-country-etls/SKILL.md`
- Modify: `.claude/skills/dispatching-country-etls/SKILL.md`
- Test: `tests/test_country_etl_issue_skills.py`

**Interfaces:** An open `ETL: <Country>` issue labelled `etl-country` leads to evidence-bearing comments, state labels, and a PR with `Closes #<issue-number>`.

- [ ] Write a failing content-contract test: both skill files contain `at least every 30 minutes` but contain neither `COUNTRIES.md` nor `sync_country_etl_issues`; the dispatching skill contains `Closes #<issue-number>`.
- [ ] Run `uv run pytest tests/test_country_etl_issue_skills.py -q`; confirm it fails against the current checklist-driven dispatching skill.
- [ ] Add `Progress reporting` to `adding-country-etls`: comment after source selection, DTM smoke result, adapter completion, verification, and PR/blocker, including command or commit evidence each time.
- [ ] Rewrite `dispatching-country-etls` to accept explicit issue numbers, verify an open `etl-country` issue, apply `in-progress`, dispatch agents by issue, change successful work to `needs-review`, change blockers to `blocked`, and report issue/PR links. Its prompt requires the evidence comments and `Closes #<issue-number>`.
- [ ] Run `uv run pytest tests/test_country_etl_issue_skills.py -q`; confirm it passes; commit `docs: track country ETL work in issues`.

### Task 3: Verify the finished workflow

**Files:** `scripts/sync_country_etl_issues.py`, the two skill files, and their test files.

- [ ] Run `uv run pytest tests/test_sync_country_etl_issues.py tests/test_country_etl_issue_skills.py -q`; expect PASS.
- [ ] Run `just check`; expect ruff, mypy, and vulture to pass.
- [ ] Run `uv run python scripts/sync_country_etl_issues.py --help`; expect options `--countries-file` and `--apply` without network activity.
