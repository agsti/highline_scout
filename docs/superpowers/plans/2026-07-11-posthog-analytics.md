# PostHog Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore PostHog product analytics to the Vite/React frontend (lost when `web/` was deleted in `c731d26`) and add a deliberately thin backend telemetry layer: one threshold-triggered `slow_request` event plus GlitchTip error reporting.

**Architecture:** The frontend carries user-intent analytics (autocapture + four committed-action events). The backend emits **no per-request events** — only a `slow_request` when a handler exceeds a threshold — and routes errors to the self-hosted GlitchTip via `sentry_sdk`. Both sides are disabled by default and only activate in production.

**Tech Stack:** `posthog-js` (frontend), `posthog` + `sentry-sdk[fastapi]` (backend), pydantic-settings, Starlette `BaseHTTPMiddleware`, vitest, pytest, sops+age.

**Spec:** `docs/superpowers/specs/2026-07-11-posthog-analytics-design.md`

## Global Constraints

- PostHog project key (frontend source, non-secret write-only ingestion key): `phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst`
- PostHog host: `https://eu.i.posthog.com` (EU data residency)
- `person_profiles: 'always'` on the frontend (anonymous public site, real unique-visitor counts)
- Backend settings use the existing `HIGHLINER_` env prefix (`highliner/core/config.py`)
- **Absent credential ⇒ disabled.** No PostHog key ⇒ no backend capture. No Sentry DSN ⇒ no Sentry. Local dev must be silent with zero configuration.
- Backend PostHog events use `distinct_id="server"` and `$process_person_profile: False` so they never create a PostHog person and never pollute frontend visitor counts.
- Backend emits **no** error events to PostHog — errors go to Sentry/GlitchTip only. No double-counting.
- `traces_sample_rate=0.0` — `/zones` fires on every map pan; tracing would flood the self-hosted GlitchTip.
- Strict mypy must stay green (`just typecheck`, `strict = true`, covers `highliner` and `tests`).
- Never send bbox/query strings to PostHog. Only route paths that FastAPI actually registered.

---

### Task 1: Frontend analytics module

**Files:**
- Modify: `frontend/package.json` (add `posthog-js`)
- Create: `frontend/src/lib/analytics.ts`
- Create: `frontend/src/lib/analytics.test.ts`
- Modify: `frontend/src/main.tsx`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `shouldEnableAnalytics(isProd: boolean, hostname: string): boolean`
  - `initAnalytics(isProd?: boolean, hostname?: string): void`
  - `capture(event: string, properties?: Record<string, unknown>): void` — **no-ops when not initialized**
  - `captureMapSettled(zoom: number, lat: number, lon: number): void` — debounced by `MAP_SETTLED_DEBOUNCE_MS`
  - `MAP_SETTLED_DEBOUNCE_MS: number` (= `2000`)

- [ ] **Step 1: Install the dependency**

```bash
cd frontend && npm install posthog-js
```

Expected: `posthog-js` appears in `dependencies` in `frontend/package.json`, and `package-lock.json` updates.

- [ ] **Step 2: Write the failing tests**

Create `frontend/src/lib/analytics.test.ts`. Note the `vi.resetModules()` + dynamic `import()` — `analytics.ts` holds module-level `enabled` state, so each test needs a fresh module instance.

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

const initMock = vi.fn();
const captureMock = vi.fn();

vi.mock("posthog-js", () => ({
  default: { init: initMock, capture: captureMock },
}));

async function loadModule() {
  return import("./analytics");
}

beforeEach(() => {
  vi.resetModules();
  initMock.mockClear();
  captureMock.mockClear();
});

describe("shouldEnableAnalytics", () => {
  it("enables on a deployed production host", async () => {
    const { shouldEnableAnalytics } = await loadModule();
    expect(shouldEnableAnalytics(true, "highlinescout.com")).toBe(true);
  });

  it("stays off in a dev build", async () => {
    const { shouldEnableAnalytics } = await loadModule();
    expect(shouldEnableAnalytics(false, "highlinescout.com")).toBe(false);
  });

  it("stays off on local hosts even in a production build", async () => {
    const { shouldEnableAnalytics } = await loadModule();
    for (const host of ["localhost", "127.0.0.1", "::1", "0.0.0.0", ""]) {
      expect(shouldEnableAnalytics(true, host)).toBe(false);
    }
  });
});

describe("capture", () => {
  it("no-ops when initAnalytics was never called", async () => {
    const { capture } = await loadModule();
    capture("zone_opened", { n_pairs: 3 });
    expect(captureMock).not.toHaveBeenCalled();
  });

  it("no-ops when init was gated off", async () => {
    const { initAnalytics, capture } = await loadModule();
    initAnalytics(false, "highlinescout.com");
    capture("zone_opened", { n_pairs: 3 });
    expect(initMock).not.toHaveBeenCalled();
    expect(captureMock).not.toHaveBeenCalled();
  });

  it("initializes PostHog and forwards events when enabled", async () => {
    const { initAnalytics, capture } = await loadModule();
    initAnalytics(true, "highlinescout.com");
    expect(initMock).toHaveBeenCalledWith(
      "phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst",
      { api_host: "https://eu.i.posthog.com", person_profiles: "always" },
    );
    capture("zone_opened", { n_pairs: 3 });
    expect(captureMock).toHaveBeenCalledWith("zone_opened", { n_pairs: 3 });
  });
});

describe("captureMapSettled", () => {
  it("emits once after the debounce, collapsing a burst of pans", async () => {
    vi.useFakeTimers();
    const { initAnalytics, captureMapSettled, MAP_SETTLED_DEBOUNCE_MS } = await loadModule();
    initAnalytics(true, "highlinescout.com");

    captureMapSettled(13, 41.6, 1.83);
    captureMapSettled(14, 41.7, 1.84);
    captureMapSettled(15, 41.8, 1.85);
    expect(captureMock).not.toHaveBeenCalled();

    vi.advanceTimersByTime(MAP_SETTLED_DEBOUNCE_MS);
    expect(captureMock).toHaveBeenCalledTimes(1);
    expect(captureMock).toHaveBeenCalledWith("map_settled", {
      zoom: 15,
      lat: 41.8,
      lon: 1.85,
    });
    vi.useRealTimers();
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd frontend && npx vitest run src/lib/analytics.test.ts
```

Expected: FAIL — `Failed to resolve import "./analytics"`.

- [ ] **Step 4: Write the implementation**

Create `frontend/src/lib/analytics.ts`:

```ts
import posthog from "posthog-js";

// Write-only ingestion key: it can send events but cannot read data, so it is
// safe in client source. (Personal keys, phx_..., are secret and unused here.)
const POSTHOG_KEY = "phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst";
const POSTHOG_HOST = "https://eu.i.posthog.com";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "0.0.0.0", ""]);

export const MAP_SETTLED_DEBOUNCE_MS = 2000;

let enabled = false;
let mapSettledTimer: ReturnType<typeof setTimeout> | undefined;

// The dev-build check is the real gate; the hostname check additionally keeps a
// local `npm run build` + `vite preview` silent.
export function shouldEnableAnalytics(isProd: boolean, hostname: string): boolean {
  return isProd && !LOCAL_HOSTS.has(hostname);
}

export function initAnalytics(
  isProd: boolean = import.meta.env.PROD,
  hostname: string = window.location.hostname,
): void {
  if (!shouldEnableAnalytics(isProd, hostname)) return;
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    person_profiles: "always",
  });
  enabled = true;
}

export function capture(event: string, properties?: Record<string, unknown>): void {
  if (!enabled) return;
  posthog.capture(event, properties);
}

// Panning fires `moveend` per gesture; debouncing collapses a scroll across the
// map into the one viewport the user actually stopped on.
export function captureMapSettled(zoom: number, lat: number, lon: number): void {
  clearTimeout(mapSettledTimer);
  mapSettledTimer = setTimeout(() => {
    capture("map_settled", {
      zoom,
      lat: Number(lat.toFixed(4)),
      lon: Number(lon.toFixed(4)),
    });
  }, MAP_SETTLED_DEBOUNCE_MS);
}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd frontend && npx vitest run src/lib/analytics.test.ts
```

Expected: PASS (8 tests).

- [ ] **Step 6: Call it from the app entry point**

Modify `frontend/src/main.tsx` — add the import and call `initAnalytics()` before `render`:

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import "./styles/globals.css";
import { App } from "./App";
import { initAnalytics } from "./lib/analytics";
import { I18nProvider } from "./lib/i18n";

initAnalytics();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 7: Verify the whole frontend suite and the type build**

```bash
just test-web
cd frontend && npx tsc -b
```

Expected: all tests pass; `tsc -b` exits 0 with no output.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/analytics.ts frontend/src/lib/analytics.test.ts frontend/src/main.tsx
git commit -m "feat(web): restore PostHog, gated to production builds on deployed hosts"
```

---

### Task 2: Frontend events for filters and restriction layers

**Files:**
- Modify: `frontend/src/App.tsx:16-27` (state), `:42-53` (filters block), and the restriction controls wiring
- Create: `frontend/src/App.analytics.test.tsx`

**Interfaces:**
- Consumes: `capture` from `@/lib/analytics` (Task 1).
- Produces: events `filter_changed` (`{ filter: "max_len" | "min_exposure", value: number }`) and `restriction_layer_toggled` (`{ layer: string, enabled: boolean }`).

`App.tsx` already separates `onMaxLenCommit` from `onMaxLenChange` (`FilterControls.tsx:11-14` maps them to Radix's `onValueCommit`/`onValueChange`). Bind analytics to the **commit** callbacks only — that is what structurally prevents an event per drag frame.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/App.analytics.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { I18nProvider } from "./lib/i18n";

const captureMock = vi.fn();
vi.mock("./lib/analytics", () => ({
  capture: (event: string, properties?: Record<string, unknown>) =>
    captureMock(event, properties),
  captureMapSettled: vi.fn(),
  initAnalytics: vi.fn(),
  MAP_SETTLED_DEBOUNCE_MS: 2000,
}));

vi.mock("./lib/api", () => ({
  fetchRestrictionLayers: vi.fn().mockResolvedValue([
    { id: "zepa", label: "ZEPA", tooltip: "", highlight: "", color: "#f00" },
  ]),
}));

vi.mock("./components/map/MapView", () => ({
  MapView: () => <div data-testid="map" />,
}));

beforeEach(() => {
  captureMock.mockClear();
});

describe("App analytics", () => {
  it("emits filter_changed once when a slider commits", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const sliders = screen.getAllByRole("slider");
    sliders[0].focus();
    await user.keyboard("{ArrowRight}");

    const filterEvents = captureMock.mock.calls.filter(([event]) => event === "filter_changed");
    expect(filterEvents).toHaveLength(1);
    expect(filterEvents[0][1]).toEqual({ filter: "max_len", value: 151 });
  });

  it("emits restriction_layer_toggled when a layer is enabled", async () => {
    const user = userEvent.setup();
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const checkbox = await screen.findByRole("checkbox", { name: /ZEPA/i });
    await user.click(checkbox);

    expect(captureMock).toHaveBeenCalledWith("restriction_layer_toggled", {
      layer: "zepa",
      enabled: true,
    });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/App.analytics.test.tsx
```

Expected: FAIL — no `filter_changed` calls recorded (`expect(filterEvents).toHaveLength(1)` gets `0`).

- [ ] **Step 3: Wire the commit handlers in `App.tsx`**

Add the import:

```tsx
import { capture } from "./lib/analytics";
```

Add these callbacks inside `App()`, after the existing `handleViewportChange`:

```tsx
  const handleMaxLenCommit = useCallback((value: number) => {
    setMaxLen(value);
    capture("filter_changed", { filter: "max_len", value });
  }, []);

  const handleMinExposureCommit = useCallback((value: number) => {
    setMinExposure(value);
    capture("filter_changed", { filter: "min_exposure", value });
  }, []);

  const handleEnabledRestrictionsChange = useCallback(
    (next: string[]) => {
      setEnabledRestrictions((previous) => {
        const before = new Set(previous);
        const after = new Set(next);
        for (const layer of next) {
          if (!before.has(layer)) capture("restriction_layer_toggled", { layer, enabled: true });
        }
        for (const layer of previous) {
          if (!after.has(layer)) capture("restriction_layer_toggled", { layer, enabled: false });
        }
        return next;
      });
    },
    [],
  );
```

Then swap the commit props in the `filters` block so they point at the new handlers (leave `onMaxLenChange`/`onMinExposureChange` on the bare setters — those fire per drag frame and must stay analytics-free):

```tsx
    <FilterControls
      maxLen={maxLen}
      minExposure={minExposure}
      showAnchors={showAnchors}
      onMaxLenChange={setMaxLen}
      onMaxLenCommit={handleMaxLenCommit}
      onMinExposureChange={setMinExposure}
      onMinExposureCommit={handleMinExposureCommit}
      onShowAnchorsChange={setShowAnchors}
    />
```

And point `RestrictionLayerControls`' `onEnabledChange` at `handleEnabledRestrictionsChange` instead of `setEnabledRestrictions`.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/App.analytics.test.tsx
```

Expected: PASS (2 tests).

- [ ] **Step 5: Run the full suite and typecheck**

```bash
just test-web
cd frontend && npx tsc -b
```

Expected: all green — in particular the existing `App.test.tsx` and `AppShell.test.tsx` must still pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.analytics.test.tsx
git commit -m "feat(web): capture filter_changed and restriction_layer_toggled on commit"
```

---

### Task 3: Frontend events for zones and map viewport

**Files:**
- Modify: `frontend/src/components/map/leafletLayers.ts:16-28` (`createZoneLayer`)
- Modify: `frontend/src/components/map/MapView.tsx` (the `moveend` handler registered in the map-init `useEffect`)
- Create: `frontend/src/components/map/leafletLayers.analytics.test.ts`

**Interfaces:**
- Consumes: `capture`, `captureMapSettled` from `@/lib/analytics` (Task 1).
- Produces: events `zone_opened` (`{ length_min, length_max, height_max, n_pairs }`) and `map_settled` (`{ zoom, lat, lon }`).

`ZoneProperties` (`frontend/src/types/highliner.ts:8-15`) is `{ height_min, height_max, length_min, length_max, n_anchors, n_pairs }` — there is **no** `exposure_m` field. Use only the fields listed above.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/map/leafletLayers.analytics.test.ts`:

```ts
import L from "leaflet";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createZoneLayer } from "./leafletLayers";
import type { ZoneFeatureCollection } from "@/types/highliner";

const captureMock = vi.fn();
vi.mock("@/lib/analytics", () => ({
  capture: (event: string, properties?: Record<string, unknown>) =>
    captureMock(event, properties),
}));

const t = ((key: string) => key) as never;

const zones: ZoneFeatureCollection = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [[[1.8, 41.6], [1.81, 41.6], [1.81, 41.61], [1.8, 41.6]]],
      },
      properties: {
        height_min: 20,
        height_max: 45,
        length_min: 30,
        length_max: 90,
        n_anchors: 4,
        n_pairs: 3,
      },
    },
  ],
};

beforeEach(() => {
  captureMock.mockClear();
});

describe("createZoneLayer", () => {
  it("emits zone_opened when a zone popup opens", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const map = L.map(container).setView([41.6, 1.8], 14);

    const layer = createZoneLayer(t);
    layer.addTo(map);
    layer.addData(zones);

    const zone = layer.getLayers()[0] as L.Layer;
    zone.openPopup();

    expect(captureMock).toHaveBeenCalledWith("zone_opened", {
      length_min: 30,
      length_max: 90,
      height_max: 45,
      n_pairs: 3,
    });

    map.remove();
    container.remove();
  });

  it("does not emit before the popup is opened", () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const map = L.map(container).setView([41.6, 1.8], 14);

    const layer = createZoneLayer(t);
    layer.addTo(map);
    layer.addData(zones);

    expect(captureMock).not.toHaveBeenCalled();

    map.remove();
    container.remove();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/components/map/leafletLayers.analytics.test.ts
```

Expected: FAIL — `captureMock` was not called.

- [ ] **Step 3: Emit `zone_opened` from `createZoneLayer`**

In `frontend/src/components/map/leafletLayers.ts`, add the import:

```ts
import { capture } from "@/lib/analytics";
```

and replace `createZoneLayer` with:

```ts
export function createZoneLayer(t: T): L.GeoJSON {
  return L.geoJSON(undefined, {
    style: () => ({
      color: ZONE_COLOR,
      weight: 2,
      fillOpacity: 0.35,
    }),
    onEachFeature: (feature, layer) => {
      const zone = feature as ZoneFeature;
      layer.bindPopup(zonePopupHtml(zone.properties, t));
      layer.on("popupopen", () => {
        const { length_min, length_max, height_max, n_pairs } = zone.properties;
        capture("zone_opened", { length_min, length_max, height_max, n_pairs });
      });
    },
  });
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/components/map/leafletLayers.analytics.test.ts
```

Expected: PASS (2 tests).

- [ ] **Step 5: Emit `map_settled` from `MapView`**

In `frontend/src/components/map/MapView.tsx`, add the import:

```ts
import { captureMapSettled } from "@/lib/analytics";
```

and add one line to the existing `moveend` handler inside the map-init `useEffect` (the handler that already calls `onViewportChange` and `publishViewState`):

```ts
    map.on("moveend", () => {
      if (keepContextMenuForMoveRef.current) {
        keepContextMenuForMoveRef.current = false;
      } else {
        setContextMenu(null);
      }
      onViewportChange(map);
      publishViewState(map);
      const center = map.getCenter();
      captureMapSettled(map.getZoom(), center.lat, center.lng);
      setViewportTick((value) => value + 1);
    });
```

The debounce lives inside `captureMapSettled`, so a burst of pans collapses to the one viewport the user stopped on.

- [ ] **Step 6: Run the full suite and typecheck**

```bash
just test-web
cd frontend && npx tsc -b
```

Expected: all green, including the existing `MapView.test.tsx`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/map/leafletLayers.ts frontend/src/components/map/leafletLayers.analytics.test.ts frontend/src/components/map/MapView.tsx
git commit -m "feat(web): capture zone_opened on popup and debounced map_settled"
```

---

### Task 4: Backend telemetry settings

**Files:**
- Modify: `highliner/core/config.py` (the `Settings` class)
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings` gains `posthog_key: str | None`, `posthog_host: str`, `sentry_dsn: str | None`, `environment: str`, `slow_request_ms: float`. All read from `HIGHLINER_`-prefixed env vars. `config.settings` remains the module-level instance.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
def test_telemetry_settings_default_to_disabled() -> None:
    from highliner.core.config import Settings

    settings = Settings()
    # Absent credentials mean telemetry is off, so local dev is silent with no
    # configuration at all.
    assert settings.posthog_key is None
    assert settings.sentry_dsn is None
    assert settings.environment == "development"
    assert settings.posthog_host == "https://eu.i.posthog.com"
    assert settings.slow_request_ms == 1000.0


def test_telemetry_settings_read_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.core.config import Settings

    monkeypatch.setenv("HIGHLINER_POSTHOG_KEY", "phc_test")
    monkeypatch.setenv("HIGHLINER_SENTRY_DSN", "https://x@glitch.example.com/2")
    monkeypatch.setenv("HIGHLINER_ENVIRONMENT", "production")
    monkeypatch.setenv("HIGHLINER_SLOW_REQUEST_MS", "250")

    settings = Settings()
    assert settings.posthog_key == "phc_test"
    assert settings.sentry_dsn == "https://x@glitch.example.com/2"
    assert settings.environment == "production"
    assert settings.slow_request_ms == 250.0
```

Add `import pytest` at the top of `tests/test_config.py` (it currently has no imports beyond `config`).

- [ ] **Step 2: Run the tests to verify they fail**

```bash
just test tests/test_config.py -v
```

Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'posthog_key'`.

- [ ] **Step 3: Add the fields**

In `highliner/core/config.py`, extend `Settings` (keep the existing `data_dir` field and the `DATA_DIR` module constant untouched):

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HIGHLINER_")

    # Where ingested rasters/anchors live. Relative to the repo root, which is
    # always the working directory the app is run from.
    data_dir: Path = Path("data")

    # Telemetry. Every credential is optional and absent means disabled, so a
    # dev machine sends nothing without any configuration.
    posthog_key: str | None = None
    posthog_host: str = "https://eu.i.posthog.com"
    sentry_dsn: str | None = None
    environment: str = "development"
    slow_request_ms: float = 1000.0
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
just test tests/test_config.py -v
just typecheck
```

Expected: PASS; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add highliner/core/config.py tests/test_config.py
git commit -m "feat: telemetry settings, disabled unless credentials are configured"
```

---

### Task 5: Backend telemetry module

**Files:**
- Modify: `pyproject.toml` (dependencies), `uv.lock`
- Create: `highliner/core/telemetry.py`
- Create: `tests/test_telemetry.py`

**Interfaces:**
- Consumes: `Settings` (Task 4).
- Produces:
  - `SERVER_DISTINCT_ID: str` (= `"server"`)
  - `init_sentry(settings: Settings) -> bool` — `True` if initialized
  - `init_posthog(settings: Settings) -> bool` — `True` if initialized
  - `capture_server_event(event: str, properties: dict[str, Any]) -> None` — **no-ops unless PostHog was armed**
  - `shutdown_telemetry() -> None`
  - `api_paths(app: FastAPI) -> frozenset[str]`
  - `SlowRequestMiddleware(app, *, threshold_ms: float, environment: str, known_paths: frozenset[str], capture: Callable[[str, dict[str, Any]], None] | None = None)`

**Why `capture_server_event` and not `posthog.capture` directly:** the middleware must resolve its capture function **at call time**, not bind it at construction. Binding early would (a) make the "sends nothing when unconfigured" test pass vacuously, since monkeypatching afterwards could not reach the bound reference, and (b) let an unconfigured server call into an unarmed PostHog client the moment a request crossed the threshold. `capture_server_event` no-ops when no key is configured — the same shape as the frontend's `capture()`.

**Why `known_paths`:** the raw request path must never become an event property directly — `app.py` mounts `StaticFiles` at `/`, so every hashed asset filename would become a distinct property value. Deriving the set of real API paths from `app.routes` collapses everything else to `"other"` and can never drift out of sync with the routers. Every API route is a static path (`/zones`, `/anchors`, `/density`, `/restrictions`, `/restrictions/layers`, `/regions`) with its parameters in the query string, so the path alone is already the route template and no bbox can leak.

- [ ] **Step 1: Add the dependencies**

```bash
uv add posthog "sentry-sdk[fastapi]"
```

Expected: both appear in `[project].dependencies` in `pyproject.toml`; `uv.lock` updates.

- [ ] **Step 2: Confirm the `posthog.capture` signature**

The kwarg order changed between posthog-python 3.x (`capture(distinct_id, event, properties)`) and 6.x (`capture(event, distinct_id=..., properties=...)`). Calling with **all keyword arguments** is compatible with both, which is what this plan does. Confirm the installed version accepts them:

```bash
uv run python -c "import inspect, posthog; print(posthog.__version__); print(inspect.signature(posthog.capture))"
```

Expected: a signature containing both `distinct_id` and `event` as accepted keyword arguments. If it does not, stop and report — do not guess.

- [ ] **Step 3: Write the failing tests**

Create `tests/test_telemetry.py`:

```python
import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from highliner.core import telemetry
from highliner.core.config import Settings
from highliner.core.telemetry import (SERVER_DISTINCT_ID, SlowRequestMiddleware,
                                      api_paths, capture_server_event,
                                      init_posthog, init_sentry)


class FakeCapture:
    """Stand-in for capture_server_event that records instead of sending."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, event: str, properties: dict[str, Any]) -> None:
        self.calls.append((event, properties))


def _app(capture: FakeCapture, threshold_ms: float) -> FastAPI:
    app = FastAPI()

    @app.get("/zones")
    def zones() -> dict[str, str]:
        return {"ok": "fast"}

    @app.get("/slow")
    def slow() -> dict[str, str]:
        time.sleep(0.05)
        return {"ok": "slow"}

    app.add_middleware(
        SlowRequestMiddleware,
        threshold_ms=threshold_ms,
        environment="test",
        known_paths=api_paths(app),
        capture=capture,
    )
    return app


def test_fast_request_emits_nothing() -> None:
    capture = FakeCapture()
    client = TestClient(_app(capture, threshold_ms=1000.0))

    assert client.get("/zones").status_code == 200

    assert capture.calls == []


def test_slow_request_emits_one_event() -> None:
    capture = FakeCapture()
    client = TestClient(_app(capture, threshold_ms=10.0))

    assert client.get("/slow").status_code == 200

    assert len(capture.calls) == 1
    event, props = capture.calls[0]
    assert event == "slow_request"
    assert props["route"] == "/slow"
    assert props["method"] == "GET"
    assert props["status_code"] == 200
    assert props["duration_ms"] >= 50.0
    assert props["environment"] == "test"
    # Keeps these system events out of person counts.
    assert props["$process_person_profile"] is False


def test_unknown_paths_collapse_to_other() -> None:
    """A hashed static asset must not become its own property value."""
    capture = FakeCapture()
    client = TestClient(_app(capture, threshold_ms=0.0))

    client.get("/zones")

    assert capture.calls[0][1]["route"] == "/zones"

    capture.calls.clear()
    # 404s go through the middleware too, and their paths are unbounded.
    client.get("/assets/index-a1b2c3d4.js")

    assert capture.calls[0][1]["route"] == "other"


def test_query_string_never_reaches_properties() -> None:
    capture = FakeCapture()
    client = TestClient(_app(capture, threshold_ms=0.0))

    client.get("/zones?bbox=1,2,3,4&max_len=150")

    event, props = capture.calls[0]
    assert props["route"] == "/zones"
    assert "bbox" not in str(props)


def test_api_paths_lists_only_registered_routes() -> None:
    app = _app(FakeCapture(), threshold_ms=1000.0)

    assert api_paths(app) == frozenset({"/zones", "/slow"})


def test_inits_are_noops_without_credentials() -> None:
    assert init_posthog(Settings(posthog_key=None)) is False
    assert init_sentry(Settings(sentry_dsn=None)) is False


def test_capture_server_event_is_silent_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unconfigured server must never call into an unarmed PostHog client."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(telemetry.posthog, "capture",
                        lambda **kwargs: calls.append(kwargs))

    init_posthog(Settings(posthog_key=None))
    capture_server_event("slow_request", {"route": "/zones"})

    assert calls == []


def test_capture_server_event_sends_when_armed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(telemetry.posthog, "capture",
                        lambda **kwargs: calls.append(kwargs))

    try:
        assert init_posthog(Settings(posthog_key="phc_test")) is True
        capture_server_event("slow_request", {"route": "/zones"})
    finally:
        # Module-level flag: leave it off so later tests stay silent.
        init_posthog(Settings(posthog_key=None))

    assert len(calls) == 1
    assert calls[0]["distinct_id"] == SERVER_DISTINCT_ID
    assert calls[0]["event"] == "slow_request"
    assert calls[0]["properties"] == {"route": "/zones"}
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
just test tests/test_telemetry.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.core.telemetry'`.

- [ ] **Step 5: Write the implementation**

Create `highliner/core/telemetry.py`:

```python
"""Product analytics (PostHog) and error reporting (GlitchTip via Sentry).

Deliberately thin. The backend only ever sees viewport reads — a slider drag or
a map pan fires many /zones requests — so per-request events would record
traffic, not intent. User intent is captured in the browser instead. Here we
emit exactly one thing the browser cannot see: a request that was too slow.

Errors are *not* sent to PostHog; they go to GlitchTip through sentry_sdk, so
nothing is counted twice.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import posthog
import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from highliner.core.config import Settings

# Backend events are anonymous system events: no client distinct_id is forwarded
# and no person profile is created (see $process_person_profile below), so they
# never pollute the frontend's unique-visitor counts.
SERVER_DISTINCT_ID = "server"


def init_sentry(settings: Settings) -> bool:
    """Send unhandled exceptions to GlitchTip. No DSN configured means no-op."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        # /zones fires on every map pan; tracing it would flood the self-hosted
        # GlitchTip with transactions that add nothing over `slow_request`.
        traces_sample_rate=0.0,
    )
    return True


_posthog_enabled = False


def init_posthog(settings: Settings) -> bool:
    """Arm the PostHog client. No key configured means no-op."""
    global _posthog_enabled
    if not settings.posthog_key:
        _posthog_enabled = False
        return False
    posthog.project_api_key = settings.posthog_key
    posthog.host = settings.posthog_host
    _posthog_enabled = True
    return True


def capture_server_event(event: str, properties: dict[str, Any]) -> None:
    """Send an anonymous system event. No-op unless PostHog was armed.

    Mirrors the frontend's capture(): callers never have to check whether
    telemetry is configured, and an unconfigured server never touches the
    network. All-keyword call so it works across posthog-python 3.x and 6.x,
    whose positional order differs.
    """
    if not _posthog_enabled:
        return
    posthog.capture(
        distinct_id=SERVER_DISTINCT_ID,
        event=event,
        properties=properties,
    )


def shutdown_telemetry() -> None:
    """Flush the PostHog queue; its sender is a background thread."""
    if not _posthog_enabled:
        return
    posthog.shutdown()


def api_paths(app: FastAPI) -> frozenset[str]:
    """The paths FastAPI actually registered.

    Anything else — notably every hashed asset under the StaticFiles mount, and
    every 404 — collapses to "other" so unbounded paths can't explode event
    property cardinality.
    """
    return frozenset(
        route.path for route in app.routes if isinstance(route, APIRoute)
    )


class SlowRequestMiddleware(BaseHTTPMiddleware):
    """Emit one `slow_request` event per request that exceeds the threshold.

    Emits nothing for a normal request. That is the point: the alternative — an
    event per request — would bill for recording the same map pan forty times.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        threshold_ms: float,
        environment: str,
        known_paths: frozenset[str],
        capture: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(app)
        self.threshold_ms = threshold_ms
        self.environment = environment
        self.known_paths = known_paths
        self._capture = capture or capture_server_event

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000.0

        if duration_ms >= self.threshold_ms:
            path = request.url.path
            properties: dict[str, Any] = {
                # Path only — never request.url, which carries the bbox.
                "route": path if path in self.known_paths else "other",
                "method": request.method,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 1),
                "environment": self.environment,
                "$process_person_profile": False,
            }
            self._capture("slow_request", properties)
        return response
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
just test tests/test_telemetry.py -v
just typecheck
```

Expected: PASS. If mypy reports missing stubs for `posthog`, add it to the existing `ignore_missing_imports` override list in `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = [
    "rasterio.*",
    "geopandas.*",
    "scipy.*",
    "pyarrow.*",
    "shapely.*",
    "affine.*",
    "pandas.*",
    "posthog.*",
]
ignore_missing_imports = true
```

Only add it if mypy actually complains — `sentry-sdk` ships `py.typed` and should need nothing.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock highliner/core/telemetry.py tests/test_telemetry.py
git commit -m "feat: slow_request telemetry and GlitchTip error reporting"
```

---

### Task 6: Wire telemetry into the app

**Files:**
- Modify: `highliner/app.py`
- Modify: `tests/test_api.py` (append)
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: `init_sentry`, `init_posthog`, `shutdown_telemetry`, `api_paths`, `SlowRequestMiddleware` (Task 5); `config.settings` (Task 4).
- Produces: `create_app()` returns an app with `SlowRequestMiddleware` installed and telemetry initialized from `config.settings`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api.py`:

```python
def test_app_installs_slow_request_middleware() -> None:
    from highliner.core.telemetry import SlowRequestMiddleware

    app = create_app()

    assert any(m.cls is SlowRequestMiddleware for m in app.user_middleware)


def test_app_sends_nothing_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default (unconfigured) app must not attempt any telemetry IO.

    Threshold is forced to 0 so every request crosses it — if the disabled-state
    guard were missing, this would call into an unarmed PostHog client.
    """
    from highliner.core import telemetry

    monkeypatch.setattr(config.settings, "slow_request_ms", 0.0)
    calls: list[object] = []
    monkeypatch.setattr(telemetry.posthog, "capture",
                        lambda **kwargs: calls.append(kwargs))

    client = TestClient(create_app(tmp_path))
    client.get("/regions")

    assert calls == []
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
just test tests/test_api.py -k middleware -v
```

Expected: FAIL — no `SlowRequestMiddleware` in `app.user_middleware`.

- [ ] **Step 3: Wire it into `create_app`**

Rewrite `highliner/app.py`:

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from highliner.core import config
from highliner.core.telemetry import (SlowRequestMiddleware, api_paths,
                                      init_posthog, init_sentry,
                                      shutdown_telemetry)
from highliner.router import (anchors, density, regions, restrictions, zones)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    shutdown_telemetry()


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or config.DATA_DIR)

    # No-ops unless the corresponding credential is configured, so a dev machine
    # sends nothing.
    init_sentry(config.settings)
    init_posthog(config.settings)

    app = FastAPI(title="Highliner Finder", lifespan=_lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    # App-wide state the routers read via highliner.router.deps.
    app.state.data_dir = data_dir

    for module in (regions, zones, anchors, density, restrictions):
        app.include_router(module.router)

    # After include_router, so the known-path set covers every API route and
    # collapses everything else (static assets, 404s) to "other".
    app.add_middleware(
        SlowRequestMiddleware,
        threshold_ms=config.settings.slow_request_ms,
        environment=config.settings.environment,
        known_paths=api_paths(app),
    )

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True),
                  name="frontend")

    return app


app = create_app()
```

Note the removed `Response`/`Scope` imports — they were unused in the original file.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
just test tests/test_api.py -v
just typecheck
```

Expected: PASS — including every pre-existing API test.

- [ ] **Step 5: Run the full backend suite**

```bash
just test
```

Expected: the whole suite green. `create_app()` is used across `test_api.py`, `test_density_endpoint.py`, `test_restrictions.py`, `test_smoke.py` and `test_integration.py`; none may regress.

- [ ] **Step 6: Document it in `AGENTS.md`**

Add a short `## Telemetry` section after the "Setup & commands" section:

```markdown
## Telemetry

Analytics and error reporting are **off unless configured**, so local dev sends
nothing and needs no setup.

- **Frontend** (`frontend/src/lib/analytics.ts`) — PostHog, initialized only in a
  production build on a non-local hostname. Autocapture plus four events bound to
  committed actions: `filter_changed`, `zone_opened`, `restriction_layer_toggled`,
  and a debounced `map_settled`. Never bind analytics to a slider's
  `onValueChange` or to a raw `moveend` — those fire per drag frame.
- **Backend** (`highliner/core/telemetry.py`) — deliberately thin. The server
  only sees viewport reads, so it emits **no per-request events**: just a
  `slow_request` when a handler exceeds `HIGHLINER_SLOW_REQUEST_MS` (default
  1000). Errors go to GlitchTip via `sentry_sdk`, never to PostHog.
- **Config** — `HIGHLINER_POSTHOG_KEY`, `HIGHLINER_SENTRY_DSN`,
  `HIGHLINER_ENVIRONMENT`, `HIGHLINER_SLOW_REQUEST_MS`. In production these come
  from sops-encrypted secrets in the separate `vps` repo (`highliner/secrets.enc.env`).
```

- [ ] **Step 7: Commit**

```bash
git add highliner/app.py tests/test_api.py AGENTS.md
git commit -m "feat: wire telemetry into the app factory"
```

---

### Task 7: Deploy configuration (separate `vps` repository)

**Files (all in `~/projects/vps`, a different git repo — commit there, not in `highliner_finder`):**
- Create: `~/projects/vps/highliner/secrets.enc.env`
- Modify: `~/projects/vps/highliner/docker-compose.yaml`

**Interfaces:**
- Consumes: the `HIGHLINER_`-prefixed settings from Task 4.
- Produces: nothing consumed by later tasks.

**Blocked on the operator:** the GlitchTip DSN for highliner does not exist yet — a project must be created at `https://glitch.vps.agustibau.com` (project `/1` belongs to `gplay_scrap`). Because `sentry_dsn` is optional and absent-means-disabled, **this task ships without it**: create the secrets file with the PostHog key only, and add `HIGHLINER_SENTRY_DSN` in a follow-up edit once the DSN exists. Do not invent a DSN.

- [ ] **Step 1: Confirm sops is available and the age recipient is pinned**

```bash
cd ~/projects/vps && sops --version && cat .sops.yaml
```

Expected: a sops version, and a `creation_rules` entry matching `secrets.enc.env` with recipient `age1cc8qmmsh8jcp004hcuuq7dhxfafnhecxmukmgeqhfsenqgxlturqlgk5ut`. Encryption needs only this **public** key, so no private key is required to create the file.

- [ ] **Step 2: Write the plaintext env file and encrypt it**

`secrets.env` is gitignored (`**/secrets.env`), so the intermediate never gets committed.

```bash
cd ~/projects/vps
cat > highliner/secrets.env <<'EOF'
HIGHLINER_POSTHOG_KEY=phc_qwCr7DcdFB5HZPeRWjaSajQKjRD7j2ARr7ECSKTtyLst
EOF
sops -e --input-type dotenv --output-type dotenv highliner/secrets.env > highliner/secrets.enc.env
```

- [ ] **Step 3: Verify the encrypted file is well-formed**

```bash
cd ~/projects/vps && grep -c "ENC\[" highliner/secrets.enc.env && git check-ignore highliner/secrets.env
```

Expected: `grep -c` prints at least `1` (the value is encrypted, not plaintext), and `git check-ignore` prints `highliner/secrets.env` (confirming the plaintext will not be committed).

- [ ] **Step 4: Add the env wiring to compose**

Modify `~/projects/vps/highliner/docker-compose.yaml` — the `highliner` service gains `env_file` and one more plain env var. `HIGHLINER_ENVIRONMENT` names the deployment rather than authenticating anything, so it stays in the clear alongside `HIGHLINER_DATA_DIR`:

```yaml
services:
  highliner:
    image: ghcr.io/agsti/highline_scout:latest
    container_name: highliner
    restart: unless-stopped
    environment:
      HIGHLINER_DATA_DIR: /data
      HIGHLINER_ENVIRONMENT: production
    env_file:
      # Decrypted from secrets.enc.env by the deploy workflow (sops + age).
      - ./secrets.env
```

Leave every other key in the file (`volumes`, `expose`, `labels`, `networks`) exactly as it is.

- [ ] **Step 5: Verify compose still parses**

```bash
cd ~/projects/vps/highliner && sops -d ../highliner/secrets.enc.env > secrets.env && docker compose config >/dev/null && echo OK
```

Expected: `OK`. (This step needs the age private key at `~/.config/sops/age/keys.txt`. If it is absent, skip it and note that compose was not validated locally — the deploy workflow decrypts with the `SOPS_AGE_KEY` repo secret.)

- [ ] **Step 6: Commit in the `vps` repo**

```bash
cd ~/projects/vps
git add highliner/secrets.enc.env highliner/docker-compose.yaml
git commit -m "feat(highliner): PostHog key via sops, production environment tag"
```

- [ ] **Step 7: Report what remains**

Tell the user, explicitly:
1. A GlitchTip project for highliner must be created to obtain the DSN; until then backend error reporting stays inert (by design, not by accident).
2. Once they have it, add `HIGHLINER_SENTRY_DSN=...` via `./edit_secrets.sh highliner` and push — no code change needed.
3. The `vps` repo commit is **not** pushed by this plan. Deployment happens when they push.

---

## Verification (after all tasks)

- [ ] `just test` — full backend suite green
- [ ] `just typecheck` — strict mypy clean
- [ ] `just test-web` — full frontend suite green
- [ ] `cd frontend && npx tsc -b` — no type errors
- [ ] `just dev` + `just dev-web`, open `http://localhost:5173`, pan the map, drag both sliders, open a zone popup, toggle a restriction layer. In the Network tab: **zero** requests to `*.i.posthog.com`. This is the load-bearing check — it proves the production gate holds.
- [ ] `cd frontend && npm run build && npm run preview` — still zero PostHog requests (the hostname latch catches a local production build).
