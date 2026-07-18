# Python Coverage Gate Design

## Goal

Prevent Python test coverage from falling below the repository's current
branch-aware baseline.

## Design

Add `pytest-cov` to the development dependencies and configure Coverage.py in
`pyproject.toml` to measure every Python file under `highliner/` and `scripts/`.
Branch measurement is enabled, report precision is two decimal places, and the
committed failure threshold is the measured baseline of 81.10%.

The existing CI test step will run pytest with coverage collection. A following,
separately named coverage step will render the report and enforce the configured
threshold. This avoids running the 286-test Python suite twice while keeping the
coverage gate visible as its own CI step.

## Failure Behavior

Test failures stop CI in the existing test step. If tests pass but combined line
and branch coverage is below 81.10%, the coverage-report step exits nonzero and
the `check` job fails. All source files are included, even when they were never
imported by the test suite.

## Verification

A project-level regression test will assert that the coverage source roots,
branch setting, precision, failure threshold, dependency, and CI commands remain
wired together. The test will be written first and observed failing before the
configuration is added. Final verification will run that focused test, the
coverage-enabled Python suite, and the repository checks.

## Scope

This gate covers Python only. Frontend Vitest and browser E2E coverage are
unchanged. The baseline does not rise automatically after coverage improvements;
raising the committed threshold is an explicit follow-up change.
