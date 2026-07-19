# Parallel CI Checks Design

## Goal

Reduce GitHub Actions feedback time by running the independent quality and test
groups concurrently. Keep the local `just check` behavior unchanged.

## Workflow structure

Replace the current sequential `check` job with four independent worker jobs:

- `python-quality`: install Python dependencies, then run Ruff, the file-length
  cap, mypy, and vulture. These relatively short static checks remain sequential
  within one runner to avoid repeating the same Python setup four times.
- `python-tests`: install Python dependencies, run pytest with coverage, then
  enforce the existing coverage report threshold.
- `frontend-tests`: install Node dependencies and run Vitest.
- `browser-e2e`: install both Python and Node dependencies, install Playwright
  Chromium, run the browser tests, and upload the existing diagnostic artifacts
  on failure. Both language environments are required because Playwright starts
  the FastAPI and Vite development servers.

Because none of these jobs depends on another, GitHub Actions schedules them in
parallel.

## Compatibility gate

Add a lightweight `check` job that declares all four worker jobs in `needs` and
runs even when a dependency fails or is cancelled. Its only step verifies that
every dependency result is `success`; otherwise it exits nonzero.

This preserves the existing `check` status name for branch protection and lets
the Docker job retain `needs: check`. The Docker build therefore starts only
after every worker has passed.

## Failure behavior

Each worker reports its own failure, making the failing subsystem immediately
visible. The final `check` gate also fails if any worker fails or is cancelled.
Playwright artifacts remain attached to the `browser-e2e` job.

## Verification

This is configuration-only behavior, so no product test is appropriate. Verify
the change by parsing the workflow locally, inspecting the job dependency graph,
and running the repository's existing YAML or CI lint tooling if available. The
first GitHub Actions run provides the end-to-end concurrency confirmation.
