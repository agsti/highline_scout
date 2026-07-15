# Browser E2E Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CI-run Playwright browser test that drives the real map through density, zone, and filter transitions using a tiny deterministic precomputed region.

**Architecture:** Playwright remains within `frontend/` and launches the existing FastAPI API with `HIGHLINER_DATA_DIR=tests/fixtures/e2e-data`, plus Vite on its normal proxy port. A committed mini-region includes one pairs partition and the density level requested by the low zoom. The browser test accepts the disclaimer, interacts with the production controls, and asserts real API requests plus the status text rendered by the app.

**Tech Stack:** Playwright/Chromium, Vite, React, Leaflet, FastAPI, pandas/Parquet, NumPy `.npz`, GitHub Actions, Just.

## Global Constraints

- Keep normal `data/` and `cache/` ignored; commit only `tests/fixtures/e2e-data/**`.
- Use the real FastAPI routers and Vite proxy; do not mock browser API responses.
- The fixture must be self-contained, offline, and small enough for routine CI.
- Default UI language is Catalan; set browser storage to English before navigating so E2E locators use English user-facing controls.
- Browser flow scope is density/zoom, zone display, and numeric filters only; restriction toggles remain out of scope.
- Preserve Node 20 and Python 3.12 CI versions.

---

### Task 1: Add Playwright commands and a self-starting test environment

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/playwright.config.ts`
- Modify: `justfile`

**Interfaces:**
- Consumes: FastAPI's `HIGHLINER_DATA_DIR` settings override and Vite's port `5173` proxy.
- Produces: `npm run test:e2e`, `npx playwright test`, and `just test-e2e`.

- [ ] **Step 1: Add the failing browser test command references**

Add the initial E2E test file from Task 3 with `import { test, expect } from "@playwright/test"`, then run:

```bash
cd frontend && npm run test:e2e
```

Expected: FAIL because `test:e2e` and `@playwright/test` do not exist yet.

- [ ] **Step 2: Add Playwright as a frontend development dependency**

Run:

```bash
cd frontend && npm install --save-dev @playwright/test
```

Ensure `frontend/package.json` contains:

```json
"scripts": {
  "test": "vitest run",
  "test:watch": "vitest",
  "test:e2e": "playwright test"
}
```

The command updates `frontend/package-lock.json`; do not hand-edit the lockfile.

- [ ] **Step 3: Configure Playwright to start the real backend and Vite**

Create `frontend/playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "HIGHLINER_DATA_DIR=tests/fixtures/e2e-data uv run uvicorn highliner.server.app:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/countries",
      cwd: "..",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
```

Add this Just recipe:

```just
# Drive the real FastAPI + Vite map in Chromium with the committed mini dataset.
test-e2e *args:
    cd frontend && npm run test:e2e -- {{args}}
```

- [ ] **Step 4: Verify the command now reaches Playwright**

Run:

```bash
just test-e2e --list
```

Expected: the test list includes `map interactions`; it may still fail to execute until Tasks 2 and 3 are complete.

- [ ] **Step 5: Commit the test environment**

```bash
git add frontend/package.json frontend/package-lock.json frontend/playwright.config.ts justfile
git commit -m "test: add Playwright e2e environment"
```

### Task 2: Commit the minimal precomputed E2E region

**Files:**
- Modify: `.gitignore`
- Create: `tests/fixtures/e2e-data/spain/e2e/grid.json`
- Create: `tests/fixtures/e2e-data/spain/e2e/pairs/q_0_0.parquet`
- Create: `tests/fixtures/e2e-data/spain/e2e/density/z14.npz`

**Interfaces:**
- Consumes: `highliner.etl.chunk.candidates.save_candidates`, `highliner.core.tiles.lonlat_to_tile`, and the density `.npz` schema read by `density_store`.
- Produces: an `e2e` Spain region that `/countries`, `/zones`, and `/density` discover without a special code path.

- [ ] **Step 1: Add a backend contract test for the committed fixture**

Create `tests/test_e2e_fixture.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from highliner.server.app import create_app


FIXTURE_DATA = Path("tests/fixtures/e2e-data")
VIEW = "1.82,41.58,1.84,41.60"


def test_e2e_fixture_serves_density_and_filterable_zones() -> None:
    client = TestClient(create_app(FIXTURE_DATA))

    density = client.get(
        "/density",
        params={"z": 14, "bbox_lonlat": VIEW, "country": "spain"},
    )
    zones = client.get(
        "/zones",
        params={"bbox_lonlat": VIEW, "country": "spain"},
    )
    filtered = client.get(
        "/zones",
        params={
            "bbox_lonlat": VIEW,
            "country": "spain",
            "min_exposure": 70,
        },
    )

    assert density.status_code == zones.status_code == filtered.status_code == 200
    assert len(density.json()["features"]) == 1
    assert len(zones.json()["features"]) == 2
    assert len(filtered.json()["features"]) == 1
```

- [ ] **Step 2: Run the fixture test to verify it fails**

Run:

```bash
uv run pytest tests/test_e2e_fixture.py -q
```

Expected: FAIL because `tests/fixtures/e2e-data` does not exist.

- [ ] **Step 3: Create the compact, valid precomputed files**

Add this exact `grid.json` content:

```json
{"bbox":[401000,4604000,404000,4607000],"chunk_m":3000,"crs":"EPSG:25831","dtm_source":"icgc"}
```

Use the existing `save_candidates` writer in a one-off `uv run python -c` command to create `q_0_0.parquet` with two spatially separated pairs inside that grid:

```python
Candidate(Anchor(402100, 4604700, 700, ()), Anchor(402180, 4604700, 700, ()), 80, 45, 0)
Candidate(Anchor(402800, 4605200, 700, ()), Anchor(402890, 4605200, 700, ()), 90, 80, 0)
```

Create `z14.npz` with exactly one cell at the tile containing `(1.83, 41.59)`. It uses the `np.savez` schema from `tests/test_density_store.py`: `cx`, `cy`, `n`, `max_exp`, `min_len`, `max_len`, `off`, `hl`, `he`, `hm`, `hc`. Store two histogram rows: `(8, 4, 0, 1)` and `(9, 8, 0, 1)`, so defaults show one hotspot cell and `min_exposure=70` still shows one cell. Use `z14` tile coordinates.

The generated binary files are committed products, not generated during CI. Record the one-off generation command in the commit message body or PR description; do not add a production or test helper merely to regenerate them.

- [ ] **Step 4: Permit only this fixture through the data ignore rule**

Replace the first `.gitignore` entry with:

```gitignore
data/
!tests/fixtures/
!tests/fixtures/e2e-data/
!tests/fixtures/e2e-data/**
```

This leaves all normal derived data ignored while allowing only the named fixture tree.

- [ ] **Step 5: Verify the fixture contract passes**

Run:

```bash
uv run pytest tests/test_e2e_fixture.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the fixture and contract test**

```bash
git add .gitignore tests/test_e2e_fixture.py tests/fixtures/e2e-data
git commit -m "test: add browser e2e map fixture"
```

### Task 3: Drive density, zoom, and filter behavior in Chromium

**Files:**
- Create: `frontend/e2e/map-interactions.spec.ts`

**Interfaces:**
- Consumes: `baseURL` and `webServer` entries from `frontend/playwright.config.ts`; the fixture response counts from Task 2; English translations in the existing catalog.
- Produces: a real-browser assertion of the current density-to-zones-to-density flow.

- [ ] **Step 1: Write the failing browser scenario**

Create `frontend/e2e/map-interactions.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("lang", "en"));
});

test("map interactions", async ({ page }) => {
  await page.goto("/?lat=41.59&lng=1.83&z=12");
  await page.getByRole("button", { name: "I understand" }).click();

  await expect(page.getByText("1 hotspot cells (zoom in for zones)")).toBeVisible();
  await expect(page.getByText("Zoom in to see zones")).toBeVisible();

  const zonesResponse = page.waitForResponse((response) =>
    response.url().includes("/zones?") && response.status() === 200,
  );
  await page.getByRole("button", { name: "Zoom in" }).click();
  await zonesResponse;
  await expect(page.getByText("2 zones")).toBeVisible();

  const exposureThumb = page.getByRole("slider").nth(2);
  await exposureThumb.focus();
  await exposureThumb.press("End");
  for (let step = 0; step < 230; step += 1) await exposureThumb.press("ArrowLeft");

  const filteredResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/zones" && url.searchParams.get("min_exposure") === "70";
  });
  await page.getByRole("button", { name: "Apply filters" }).click();
  await filteredResponse;
  await expect(page.getByText("1 zones")).toBeVisible();

  const densityResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/density" && response.status() === 200,
  );
  await page.getByRole("button", { name: "Zoom out" }).click();
  await densityResponse;
  await expect(page.getByText("1 hotspot cells (zoom in for zones)")).toBeVisible();
});
```

- [ ] **Step 2: Run the browser scenario to verify it fails for the intended reason**

Run:

```bash
just test-e2e e2e/map-interactions.spec.ts
```

Expected: FAIL only if a locator, fixture response, or behavior contract is incorrect. Correct the test/fixture contract until it demonstrates the current missing E2E setup rather than a timing error.

- [ ] **Step 3: Make the scenario deterministic without mocks**

Use `page.waitForResponse` before each triggering click and status-text assertions after it. If Radix's keyboard movement produces any value other than 70, replace the `End` plus 230 `ArrowLeft` loop with the smallest exact sequence that sets the observed accessible slider to 70; keep the assertion on the `/zones?min_exposure=70` request.

Do not add fixed sleeps. Do not access Leaflet internals or inject API responses. Browser behavior must stay limited to DOM controls, user keyboard input, network observations, and visible status text.

- [ ] **Step 4: Verify the test passes in headless and headed Chromium**

Run:

```bash
just test-e2e e2e/map-interactions.spec.ts
just test-e2e e2e/map-interactions.spec.ts --headed
```

Expected: both commands PASS, with the headed run visibly opening Chromium and exercising the map controls.

- [ ] **Step 5: Commit the browser flow**

```bash
git add frontend/e2e/map-interactions.spec.ts
git commit -m "test: cover map interactions in browser"
```

### Task 4: Run the browser test in CI and retain failure artifacts

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `frontend/package-lock.json`, `just test-e2e`, and Playwright's `frontend/playwright-report/` plus `frontend/test-results/` output directories.
- Produces: Chromium coverage in the existing `check` job and downloadable diagnostics when it fails.

- [ ] **Step 1: Add the expected CI invocation locally**

Run:

```bash
cd frontend && npx playwright install --with-deps chromium
cd .. && just test-e2e
```

Expected: FAIL before the workflow change only if Chromium is unavailable; after installation, PASS.

- [ ] **Step 2: Add the Chromium install, E2E run, and failure artifact steps**

After `Frontend tests (vitest)` in the `check` job, add:

```yaml
      - name: Install Playwright Chromium
        run: npx playwright install --with-deps chromium
        working-directory: frontend

      - name: Browser E2E tests
        run: just test-e2e

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

- [ ] **Step 3: Verify the modified workflow is structurally valid**

Run:

```bash
git diff --check
rg -n "Install Playwright Chromium|Browser E2E tests|Upload browser-test artifacts" .github/workflows/ci.yml
```

Expected: no whitespace errors and all three CI steps are present beneath the frontend Vitest step in job `check`.

- [ ] **Step 4: Run the complete relevant verification set**

Run:

```bash
uv run pytest tests/test_e2e_fixture.py -q
just test-web
just test-e2e
just check
```

Expected: every command PASS.

- [ ] **Step 5: Commit the CI coverage**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run browser e2e tests"
```

## Plan self-review

- Spec coverage: Tasks 1 and 3 provide Playwright/Chromium and real-browser behavior; Task 2 provides the committed standalone fixture; Task 4 provides CI execution and diagnostics; headed local execution is covered by Task 3.
- No-placeholder scan: no TODO/TBD markers or generic test instructions remain; each implementation action names files and commands.
- Interface consistency: the backend receives `HIGHLINER_DATA_DIR`, Vite retains port 5173, fixture paths match the server's `<data>/<country>/<region>` discovery, and all asserted routes are existing routes.
