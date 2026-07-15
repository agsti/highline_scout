# Browser E2E Testing Design

## Goal

Add a deterministic browser-driven smoke suite that exercises the real
FastAPI API, Vite frontend, Leaflet map, zoom controls, and numeric filters.
It must run in CI from a tiny committed precomputed dataset and be usable
locally against a developer's larger precomputed dataset when requested.

## Test stack and ownership

Use Playwright and Chromium. Browser-test source and Playwright configuration
belong in `frontend/`, alongside the React application:

```text
frontend/
  e2e/map-interactions.spec.ts
  playwright.config.ts
```

The suite starts FastAPI and Vite automatically. FastAPI receives an explicit
data-directory setting, preventing CI runs from reading a developer's ignored
`data/` tree. Vite proxies the browser's API requests to that backend, matching
local development behavior.

`just test-e2e` runs the headless suite. A frontend npm script exposes the
same command and supports Playwright's normal flags, including `--headed` for
interactive local debugging.

## Fixture data

Commit the minimal precomputed data required by the browser scenario at the
repository level:

```text
tests/fixtures/e2e-data/
  spain/e2e/
    grid.json
    pairs/
    density/
```

This location is intentionally outside both `frontend/` and the Python test
module namespace: it is a shared integration fixture consumed by the backend
and observable by the frontend. A precise `.gitignore` exception permits only
this fixture while preserving the repository-wide `data/` ignore rule.

The fixture contains at least two candidate groups in the initial viewport:
one remains after the scenario's stricter length/exposure filter and one does
not. It also contains density cells for the same viewport. This makes each
assertion deterministic without mocks or network access.

## Browser scenario

The initial test opens the fixture region at a low density zoom through the
existing URL view parameters. It performs and verifies these user-visible
transitions:

1. The map loads density mode and reports hotspot cells plus the zoom-in hint.
2. Clicking the existing zoom-in control crosses the density threshold. The
   browser observes a real `/zones` request and the visible status changes to
   a zones count.
3. Adjusting the existing numeric filter controls issues a new `/zones`
   request whose query reflects the changed filter values. The fixture causes
   the displayed zones count to change.
4. Clicking zoom-out crosses back into density mode, producing a real
   `/density` request and restoring the hotspot status/hint.

The test uses accessible control names and status text. Request predicates
assert API contract details only where no stable visual equivalent exists.
It does not test protected-area filter controls in this first scenario.

## CI and failure diagnostics

CI installs the frontend dependencies and the Playwright Chromium browser,
then runs `just test-e2e` after the normal frontend/unit checks. On failure,
upload Playwright's HTML report, screenshots, and traces as CI artifacts.

Playwright keeps traces on first retry and screenshots on failure, providing a
replayable browser record without adding artifacts to successful runs.

## Out of scope

- Replacing existing Vitest component/unit tests.
- Testing live national data or downloading terrain data in CI.
- Protected-area toggles, map context-menu actions, mobile layout, and
  visual-regression screenshots; these can be separate scenarios later.
