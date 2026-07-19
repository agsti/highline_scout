# Parallel CI Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the independent CI check groups concurrently while preserving the existing `check` status and Docker dependency.

**Architecture:** Split the sequential GitHub Actions `check` job into four independent worker jobs for Python quality, Python tests, frontend tests, and browser E2E tests. Add a final `check` aggregation job that always evaluates all worker results and fails unless every worker succeeded.

**Tech Stack:** GitHub Actions YAML, uv/Python 3.12, Node.js 20, Vitest, Playwright

## Global Constraints

- Keep the local `just check` recipe unchanged.
- Keep Ruff, the file-length cap, mypy, and vulture together in one `python_quality` job.
- Keep pytest and the coverage report together in one `python_tests` job.
- Keep Vitest isolated in `frontend_tests` and Playwright isolated in `browser_e2e`.
- Preserve the final GitHub Actions status name `check` and keep `docker` dependent on it.
- Preserve Playwright artifact upload behavior on failure.

---

### Task 1: Split and aggregate CI checks

**Files:**
- Modify: `.github/workflows/ci.yml`
- Test: `.github/workflows/ci.yml` (configuration parsing and graph inspection)

**Interfaces:**
- Consumes: Existing commands and setup steps from the sequential `check` job.
- Produces: Worker job results consumed as `needs.<job_id>.result` by the final `check` job.

- [x] **Step 1: Capture the current sequential workflow graph**

Run:

```bash
sed -n '1,130p' .github/workflows/ci.yml
```

Expected: one `check` job contains Python quality, Python tests, frontend tests,
and browser E2E steps; `docker` has `needs: check`.

- [x] **Step 2: Split the worker jobs**

Replace the original `check` job with these job IDs and contents:

```yaml
python_quality:
  name: Python quality
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Install uv
      uses: astral-sh/setup-uv@v5

    - name: Set up Python 3.12
      run: uv python install 3.12

    - name: Install dependencies
      run: uv sync --extra dev

    - name: Lint (ruff)
      run: uv run ruff check

    - name: File length cap
      run: uv run python scripts/check_file_length.py

    - name: Type check (mypy)
      run: uv run mypy

    - name: Dead code (vulture)
      run: uv run vulture

python_tests:
  name: Python tests
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Install uv
      uses: astral-sh/setup-uv@v5

    - name: Set up Python 3.12
      run: uv python install 3.12

    - name: Install dependencies
      run: uv sync --extra dev

    - name: Run tests with coverage
      run: uv run pytest --cov --cov-report= --cov-fail-under=0

    - name: Check Python coverage
      run: uv run coverage report

frontend_tests:
  name: Frontend tests
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Set up Node 20
      uses: actions/setup-node@v4
      with:
        node-version: 20
        cache: npm
        cache-dependency-path: frontend/package-lock.json

    - name: Install frontend dependencies
      run: npm ci
      working-directory: frontend

    - name: Frontend tests (vitest)
      run: npm test
      working-directory: frontend

browser_e2e:
  name: Browser E2E tests
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Install uv
      uses: astral-sh/setup-uv@v5

    - name: Set up Python 3.12
      run: uv python install 3.12

    - name: Install Python dependencies
      run: uv sync --extra dev

    - name: Set up Node 20
      uses: actions/setup-node@v4
      with:
        node-version: 20
        cache: npm
        cache-dependency-path: frontend/package-lock.json

    - name: Install frontend dependencies
      run: npm ci
      working-directory: frontend

    - name: Install Playwright Chromium
      run: npx playwright install --with-deps chromium
      working-directory: frontend

    - name: Browser E2E tests
      run: npm run test:e2e
      working-directory: frontend

    - name: Upload browser-test artifacts
      if: failure()
      uses: actions/upload-artifact@v4
      with:
        name: playwright-report
        path: |
          frontend/playwright-report/
          frontend/test-results/
        if-no-files-found: ignore
```

Copy each existing command unchanged into its corresponding worker. The browser
job must include both Python and Node setup because Playwright starts both
FastAPI and Vite servers.

- [x] **Step 3: Add the compatibility gate**

Add the final job before `docker`:

```yaml
check:
  if: ${{ always() }}
  needs:
    - python_quality
    - python_tests
    - frontend_tests
    - browser_e2e
  runs-on: ubuntu-latest
  steps:
    - name: Verify all checks passed
      env:
        PYTHON_QUALITY_RESULT: ${{ needs.python_quality.result }}
        PYTHON_TESTS_RESULT: ${{ needs.python_tests.result }}
        FRONTEND_TESTS_RESULT: ${{ needs.frontend_tests.result }}
        BROWSER_E2E_RESULT: ${{ needs.browser_e2e.result }}
      run: |
        for check_result in \
          "$PYTHON_QUALITY_RESULT" \
          "$PYTHON_TESTS_RESULT" \
          "$FRONTEND_TESTS_RESULT" \
          "$BROWSER_E2E_RESULT"
        do
          test "$check_result" = "success" || exit 1
        done
```

Leave `docker` with `needs: check`, so image building cannot start unless the
aggregation gate succeeds.

- [x] **Step 4: Validate syntax and job dependencies**

Run:

```bash
uv run python -c 'import pathlib, yaml; yaml.safe_load(pathlib.Path(".github/workflows/ci.yml").read_text())'
```

Expected: exit code 0 with no output.

Inspect the parsed job graph:

```bash
uv run python - <<'PY'
from pathlib import Path

import yaml

jobs = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())["jobs"]
workers = {"python_quality", "python_tests", "frontend_tests", "browser_e2e"}
assert all("needs" not in jobs[job] for job in workers)
assert set(jobs["check"]["needs"]) == workers
assert jobs["docker"]["needs"] == "check"
PY
```

Expected: exit code 0 with no output.

- [x] **Step 5: Review the diff and commit**

Run:

```bash
git diff --check
git diff -- .github/workflows/ci.yml
git status --short
```

Expected: no whitespace errors; only the planned CI workflow and plan document
are uncommitted.

Commit:

```bash
git add .github/workflows/ci.yml docs/superpowers/plans/2026-07-19-parallel-ci-checks.md
git commit -m "ci: run check groups in parallel"
```
