# Python Coverage Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fail CI when combined Python line and branch coverage falls below the current 81.10% baseline.

**Architecture:** Pytest-cov collects coverage during the existing Python test run using Coverage.py settings committed in `pyproject.toml`. A separate CI step renders the stored data and enforces the configured threshold, avoiding a second test-suite run.

**Tech Stack:** Python 3.12, pytest, pytest-cov/Coverage.py, GitHub Actions, uv

## Global Constraints

- Measure every Python file under `highliner/` and `scripts/`.
- Enable branch coverage.
- Report to two decimal places and fail below 81.10%.
- Keep frontend test and browser E2E workflows unchanged.
- Keep the coverage check as a separately named CI step without running pytest twice.

---

### Task 1: Add and enforce the Python coverage baseline

**Files:**
- Modify: `tests/project/test_commands.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `.github/workflows/ci.yml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: the existing `check` GitHub Actions job and its Python test step.
- Produces: Coverage.py configuration with `branch = true`, source roots `highliner` and `scripts`, `precision = 2`, and `fail_under = 81.10`; CI commands that collect and enforce that baseline.

- [ ] **Step 1: Write the failing project regression test**

Add `tomllib` and this test to `tests/project/test_commands.py`:

```python
import tomllib
from pathlib import Path


def test_ci_enforces_python_branch_coverage() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text())
    dev_dependencies = project["project"]["optional-dependencies"]["dev"]
    coverage = project["tool"]["coverage"]

    assert "pytest-cov" in dev_dependencies
    assert coverage["run"] == {
        "branch": True,
        "source": ["highliner", "scripts"],
    }
    assert coverage["report"]["precision"] == 2
    assert coverage["report"]["fail_under"] == 81.10

    workflow = Path(".github/workflows/ci.yml").read_text()
    assert (
        "run: uv run pytest --cov --cov-report= --cov-fail-under=0"
        in workflow
    )
    assert "- name: Check Python coverage" in workflow
    assert "run: uv run coverage report" in workflow
```

- [ ] **Step 2: Run the focused test and verify it fails for missing configuration**

Run:

```bash
uv run pytest tests/project/test_commands.py::test_ci_enforces_python_branch_coverage -v
```

Expected: FAIL while looking up `project["tool"]["coverage"]`, because no
coverage configuration exists yet.

- [ ] **Step 3: Add the coverage dependency and configuration**

Run:

```bash
uv add --optional dev pytest-cov
```

Add this configuration to `pyproject.toml`:

```toml
[tool.coverage.run]
branch = true
source = ["highliner", "scripts"]

[tool.coverage.report]
fail_under = 81.10
precision = 2
```

The uv command must update both `pyproject.toml` and `uv.lock`.

- [ ] **Step 4: Collect coverage in the test step and enforce it separately**

Replace the Python portion of `.github/workflows/ci.yml` with:

```yaml
      - name: Run tests with coverage
        run: uv run pytest --cov --cov-report= --cov-fail-under=0

      - name: Check Python coverage
        run: uv run coverage report
```

Add the generated local data file to `.gitignore`:

```gitignore
.coverage
```

- [ ] **Step 5: Run the focused regression test and verify it passes**

Run:

```bash
uv run pytest tests/project/test_commands.py::test_ci_enforces_python_branch_coverage -v
```

Expected: PASS.

- [ ] **Step 6: Verify the coverage gate against the current suite**

Run:

```bash
uv run pytest --cov --cov-report= --cov-fail-under=0
uv run coverage report
```

Expected: 286 tests pass; the report shows 81.10% total branch-aware coverage
and exits successfully at the 81.10% threshold.

- [ ] **Step 7: Run repository quality checks**

Run:

```bash
just check
```

Expected: ruff, file-length, mypy, vulture, and frontend tests all pass.

- [ ] **Step 8: Inspect the final change set**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only the planned configuration, lockfile,
workflow, ignore, test, and plan files are changed.

- [ ] **Step 9: Commit the implementation**

```bash
git add .github/workflows/ci.yml .gitignore pyproject.toml uv.lock \
  tests/project/test_commands.py \
  docs/superpowers/plans/2026-07-18-python-coverage-gate.md
git commit -m "ci: prevent Python coverage regressions"
```

## Self-Review

- Spec coverage: the single task adds the dependency, measures both configured
  source roots with branches, commits the current threshold, exposes a distinct
  CI gate, and leaves frontend coverage unchanged.
- Type and command consistency: the regression test asserts the same keys and
  commands that the implementation steps define.
- Scope: no coverage service, artifact upload, frontend coverage, or automatic
  threshold ratcheting is introduced.
