# Resumable Parallel Precompute Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `highliner precompute` safely resumable and chunk-parallel, then expose it through the Spain precompute wrapper.

**Architecture:** Keep the existing `data/<region>/anchors` and `data/<region>/pairs` layout. Add a worker count to `precompute`, dispatch chunks through a thread pool, write chunk outputs through temporary parquet files with atomic replaces, and give each chunk its own transient tile directory.

**Tech Stack:** Python 3.12 via `uv`, pytest, argparse, `concurrent.futures`, existing parquet repositories.

## Global Constraints

- Preserve the existing serving data contract: `grid.json`, `anchors/p_{cx}_{cy}.parquet`, and `pairs/q_{cx}_{cy}.parquet`.
- Keep `workers=1` as the default behavior.
- Treat the pair parquet as the completion marker; it is written last.
- Use TDD: write and run failing tests before production changes.

---

### Task 1: CLI worker plumbing

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `highliner/cli.py`
- Modify: `scripts/precompute_spain.py`

**Interfaces:**
- Produces: `highliner precompute --workers N`
- Produces: `scripts/precompute_spain.py --chunk-workers N`

- [ ] Write failing CLI tests that assert worker counts are forwarded.
- [ ] Run the focused CLI tests and confirm failure because `workers` is not accepted.
- [ ] Add argparse options and pass `workers` to `precompute`.
- [ ] Run the focused CLI tests and confirm pass.

### Task 2: Parallel and atomic precompute service

**Files:**
- Modify: `tests/test_precompute.py`
- Modify: `highliner/services/precompute.py`

**Interfaces:**
- Produces: `precompute(..., workers: int = 1) -> int`
- Produces: atomic chunk output writes where `q_*.parquet` is replaced last.

- [ ] Write failing service tests for worker dispatch, validation, and temp-file cleanup.
- [ ] Run focused precompute tests and confirm failure for missing `workers`.
- [ ] Implement thread-pool chunk dispatch for `workers > 1`.
- [ ] Write chunk outputs to `*.tmp-<pid>-<cx>-<cy>` files, replace anchor first, replace pair last, and remove leftover temp files.
- [ ] Use `tiles/chunk_{cx}_{cy}_{pid}` as the transient tile directory.
- [ ] Run focused precompute tests and confirm pass.

### Task 3: Final verification

**Files:**
- All modified files.

- [ ] Run `uv run pytest tests/test_cli.py tests/test_precompute.py`.
- [ ] Run `uv run mypy highliner scripts`.
- [ ] Run `uv run pytest`.
