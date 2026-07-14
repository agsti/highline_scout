# Country Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow visitors to select a precomputed country and ensure all map data is loaded, displayed, and framed only for that country.

**Architecture:** Build a country catalog from the cached `RegionEntry` index at server startup, exposing each country’s data-coverage bounds and midpoint through `GET /countries`. Keep `country` as the query parameter on all map-data routes and propagate the selected country through React state, the typed API client, layer hooks, and a menu selector that fits Leaflet to the selected bounds.

**Tech Stack:** Python 3.11, FastAPI, PyProj-backed existing geo helpers, pytest/httpx, React 18, TypeScript, Leaflet, Vitest, Testing Library.

## Global Constraints

- `grid.json` is the authoritative data source; do not create a country catalog file, ETL command, or Just recipe.
- Catalog bounds describe the union of available precomputed region coverage, not legal national borders.
- Default omitted `country` parameters to `config.DEFAULT_COUNTRY` (`"spain"`) for API compatibility.
- Every frontend zones, density, anchors, restrictions, and restriction-layer request serializes the selected `country`.
- A country change preserves filters and anchor visibility, clears selected restrictions, aborts stale layer requests, and fits the map to the catalog bounds.
- Preserve the repository limits: strict mypy, 88-column Ruff linting, cyclomatic complexity 10, no new `noqa` unless unavoidable, and a 500-line source-file cap.

---

## File structure

- Modify `highliner/server/router/deps.py`: define catalog entries and derive their bounds/centers from `RegionEntry` values.
- Create `highliner/server/router/countries.py`: serve the cached country catalog at `GET /countries`.
- Modify `highliner/server/app.py`: register the countries router and exclude `/countries` from crawlable pages in `robots.txt`.
- Modify `highliner/server/router/restrictions.py`: accept `country` on `GET /restrictions/layers`.
- Modify `tests/test_region_index.py` and `tests/test_api.py`: prove catalog geometry and route contracts.
- Modify `frontend/src/types/highliner.ts` and `frontend/src/lib/api.ts`: model country metadata and require `country` for every map-data query.
- Modify `frontend/src/components/map/MapView.tsx`, `useLeafletMap.ts`, `useZoneDensityLayer.ts`, `useAnchorLayer.ts`, and `useRestrictionLayer.ts`: receive country, clear old layers, refetch with country, and fit selected coverage bounds.
- Modify `frontend/src/App.tsx`, `FloatingNav.tsx`, and `NavMenu.tsx`: own selection state, load the catalog, reset restrictions, and render the selector.
- Modify `frontend/src/lib/i18n/strings.ts`: add equal Catalan, Spanish, and English labels for the country selector.
- Modify frontend tests closest to these units: `lib/api.test.ts`, `App.test.tsx`, `components/NavMenu.test.tsx`, and `components/map/useLeafletMap.test.tsx`.

### Task 1: Derive and serve the startup country catalog

**Files:**

- Modify: `highliner/server/router/deps.py`
- Create: `highliner/server/router/countries.py`
- Modify: `highliner/server/app.py`
- Test: `tests/test_region_index.py`
- Test: `tests/test_api.py`

**Interfaces:**

- Consumes: `list[RegionEntry]` from `build_region_index(data_dir)`.
- Produces: `CountryEntry(id: str, bounds_lonlat: LonLatBox, center_lonlat: tuple[float, float])` and `countries_from_index(index: list[RegionEntry]) -> list[CountryEntry]`.
- Produces: `GET /countries -> {"countries": [{"id", "bounds_lonlat", "center_lonlat"}]}`.

- [ ] **Step 1: Write failing unit tests for union bounds and center**

  In `tests/test_region_index.py`, add two `spain` regions with different
  `lonlat_bounds` and one `france` region, then assert country aggregation is
  sorted by ID and has the complete union and midpoint:

  ```python
  countries = deps.countries_from_index(index)
  assert [(c.id, c.bounds_lonlat, c.center_lonlat) for c in countries] == [
      ("france", (1.9, 41.6, 2.0, 41.7), (1.95, 41.65)),
      ("spain", (1.8, 41.5, 1.9, 41.6), (1.85, 41.55)),
  ]
  ```

- [ ] **Step 2: Run the new unit test and confirm it fails because the helper is absent**

  Run: `uv run pytest tests/test_region_index.py -k countries -v`

  Expected: FAIL with an `AttributeError` for `countries_from_index`.

- [ ] **Step 3: Implement immutable catalog entries and aggregation**

  Add the dataclass and a one-pass grouping helper in `deps.py`; calculate
  `min(west)`, `min(south)`, `max(east)`, and `max(north)` from each country’s
  `RegionEntry.lonlat_bounds`, then use the arithmetic midpoint:

  ```python
  @dataclass(frozen=True)
  class CountryEntry:
      id: str
      bounds_lonlat: LonLatBox
      center_lonlat: tuple[float, float]

  def countries_from_index(index: list[RegionEntry]) -> list[CountryEntry]:
      # Group entries by country, derive union bounds, and return ID-sorted rows.
  ```

  Extend `get_region_index()` to cache `country_index` at the same time it
  caches `region_index`, or add a `get_country_index(request)` accessor that
  derives and caches it from the existing region index. Do not rescan disk.

- [ ] **Step 4: Write the failing route test**

  In `tests/test_api.py`, construct Spain and France fixture regions, request
  `/countries`, and assert the endpoint returns both IDs plus four-element
  `bounds_lonlat` and two-element `center_lonlat` values. Also assert
  `/countries` returns `{"countries": []}` with an empty data directory.

- [ ] **Step 5: Run the route test and confirm it fails with 404**

  Run: `uv run pytest tests/test_api.py -k countries -v`

  Expected: FAIL because `/countries` is not registered.

- [ ] **Step 6: Implement and register the router**

  Create `countries.py` following the one-router-per-resource convention:

  ```python
  router = APIRouter()

  @router.get("/countries")
  def countries(request: Request) -> dict[str, Any]:
      return {"countries": [
          {"id": entry.id, "bounds_lonlat": list(entry.bounds_lonlat),
           "center_lonlat": list(entry.center_lonlat)}
          for entry in get_country_index(request)
      ]}
  ```

  Import/register `countries` in `server/app.py` beside the existing routers
  and add `/countries` to the robots disallow list with the other API routes.

- [ ] **Step 7: Run backend catalog tests and commit**

  Run: `uv run pytest tests/test_region_index.py tests/test_api.py -v`

  Expected: PASS.

  ```bash
  git add highliner/server/router/deps.py highliner/server/router/countries.py \
    highliner/server/app.py tests/test_region_index.py tests/test_api.py
  git commit -m "feat: expose precomputed country catalog"
  ```

### Task 2: Make every map-data API explicitly country-aware

**Files:**

- Modify: `highliner/server/router/restrictions.py`
- Modify: `highliner/server/services/restrictions.py`
- Modify: `tests/test_api.py`

**Interfaces:**

- Consumes: `country: str = config.DEFAULT_COUNTRY` on the existing endpoints.
- Produces: `layer_meta(country: str) -> list[dict[str, str]]` and
  `GET /restrictions/layers?country=<id>` while retaining the
  metadata response shape `{ "layers": [...] }`.

- [ ] **Step 1: Write the failing restriction-metadata contract test**

  In `test_restriction_layers_registry`, monkeypatch
  `restrictions_service.layer_meta` with a local function that records its
  argument, then call:

  ```python
  r = client.get("/restrictions/layers", params={"country": "france"})
  assert r.status_code == 200
  assert seen == ["france"]
  assert {row["id"] for row in r.json()["layers"]} >= {"zepa", "zec", "enp"}
  ```

  Add an assertion that the default request remains successful, documenting
  compatibility. The test proves FastAPI accepts the uniform parameter even
  though shared metadata currently does not differ per country.

- [ ] **Step 2: Run the test and confirm it fails because the router does not forward country**

  Run: `uv run pytest tests/test_api.py::test_restriction_layers_registry -v`

  Expected: FAIL with the monkeypatched `layer_meta` missing its required
  `country` argument, proving the router does not yet forward the value.

- [ ] **Step 3: Add the explicit `country` argument**

  Change the service and handler signatures to:

  ```python
  @router.get("/restrictions/layers")
  def layer_meta(country: str) -> list[dict[str, str]]:
      return [dict(spec, id=layer_id) for layer_id, spec in LAYERS.items()]

  @router.get("/restrictions/layers")
  def restriction_layers(country: str = config.DEFAULT_COUNTRY) -> dict[str, Any]:
      return {"layers": restrictions_service.layer_meta(country)}
  ```

  The service may return the common registry today, but receiving country makes
  the metadata contract explicit and leaves a single country-specific extension
  point. Keep `/zones`, `/anchors`, `/density`, `/restrictions`, and `/regions`
  behavior unchanged: they already scope reads by country.

- [ ] **Step 4: Run API regression tests and commit**

  Run: `uv run pytest tests/test_api.py tests/test_density_endpoint.py -v`

  Expected: PASS.

  ```bash
  git add highliner/server/router/restrictions.py highliner/server/services/restrictions.py \
    tests/test_api.py
  git commit -m "feat: accept country on restriction metadata"
  ```

### Task 3: Add typed frontend catalog and country query serialization

**Files:**

- Modify: `frontend/src/types/highliner.ts`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/lib/api.test.ts`

**Interfaces:**

- Consumes: `CountryEntry` API JSON from Task 1.
- Produces: `fetchCountries(signal?) -> Promise<CountryEntry[]>`,
  `fetchRestrictionLayers(country: string, signal?)`, and `country: string`
  required by `ZoneQuery`, `DensityQuery`, `ViewportQuery`, and
  `RestrictionsQuery`.

- [ ] **Step 1: Write failing API-client serialization tests**

  Expand `api.test.ts` to call every function with `country: "france"` and
  assert exact request URLs, including:

  ```typescript
  expect(fetch).toHaveBeenCalledWith(
    "/anchors?bbox_lonlat=1%2C2%2C3%2C4&country=france",
    { signal: undefined },
  );
  expect(fetch).toHaveBeenCalledWith(
    "/restrictions/layers?country=france",
    { signal: undefined },
  );
  ```

  Include `/zones`, `/density`, and `/restrictions`, and a `fetchCountries()`
  test that unwraps `{ countries }`.

- [ ] **Step 2: Run the test and confirm it fails on absent `country` query parameters**

  Run: `cd frontend && npm test -- api.test.ts`

  Expected: FAIL with URL mismatches and TypeScript call-site errors until the
  interfaces are updated.

- [ ] **Step 3: Implement the strict client interfaces and serialization**

  Add:

  ```typescript
  export interface CountryEntry {
    id: string;
    bounds_lonlat: [number, number, number, number];
    center_lonlat: [number, number];
  }
  ```

  Make `country` required on the shared query interface, append it to each
  `query()` object, and implement `fetchCountries` by unwrapping the response.
  Update the error-path `fetchZones` test call with `country: "spain"`.

- [ ] **Step 4: Run frontend API tests and commit**

  Run: `cd frontend && npm test -- api.test.ts`

  Expected: PASS.

  ```bash
  git add frontend/src/types/highliner.ts frontend/src/lib/api.ts frontend/src/lib/api.test.ts
  git commit -m "feat: serialize country in map API requests"
  ```

### Task 4: Propagate country through map hooks and fit the selected coverage

**Files:**

- Modify: `frontend/src/components/map/MapView.tsx`
- Modify: `frontend/src/components/map/useLeafletMap.ts`
- Modify: `frontend/src/components/map/useZoneDensityLayer.ts`
- Modify: `frontend/src/components/map/useAnchorLayer.ts`
- Modify: `frontend/src/components/map/useRestrictionLayer.ts`
- Test: `frontend/src/components/map/useLeafletMap.test.tsx`
- Test: `frontend/src/components/map/useZoneDensityLayer.test.tsx`
- Test: `frontend/src/components/map/useAnchorLayer.test.tsx`
- Test: `frontend/src/components/map/useRestrictionLayer.test.tsx`

**Interfaces:**

- Consumes: `country: string` and `countryBounds?: [number, number, number, number]` from App.
- Produces: Leaflet `fitBounds([[south, west], [north, east]])` after the
  selected country changes; all existing hooks call Task 3 functions with
  `country` and re-run/abort when it changes.

- [ ] **Step 1: Write failing hook tests**

  Add a country value to each hook’s test render and assert its mocked API call
  includes it. In the Leaflet hook test, rerender with:

  ```typescript
  countryBounds: [1, 41, 2, 42],
  country: "france",
  ```

  and assert the mock map receives:

  ```typescript
  expect(map.fitBounds).toHaveBeenCalledWith([[41, 1], [42, 2]]);
  ```

  Also assert country changes clear prior zones/anchors/restrictions before the
  new request resolves, preventing visible old-country features.

- [ ] **Step 2: Run hook tests and confirm they fail due to missing props and requests**

  Run: `cd frontend && npm test -- useLeafletMap.test.tsx useZoneDensityLayer.test.tsx useAnchorLayer.test.tsx useRestrictionLayer.test.tsx`

  Expected: FAIL because the hook option objects do not yet declare country or
  bounds and client calls lack the country argument.

- [ ] **Step 3: Implement country-aware map behavior**

  Add `country` to `MapViewProps` and each layer hook option. Include it in the
  corresponding effect dependency list and client request:

  ```typescript
  fetchZones({
    country: options.country,
    bboxLonLat,
    minLen: options.minLen,
    maxLen: options.maxLen,
    minExposure: options.minExposure,
  }, controller.signal);
  ```

  On country changes, reset the refs holding accumulated zones, density, and
  anchors and clear their Leaflet layers before loading. In `useLeafletMap`,
  accept `countryBounds` and add a separate effect that calls `fitBounds` only
  when the bounds tuple changes; do not recreate the map. Convert API bounds
  `[w, s, e, n]` to Leaflet corners `[[s, w], [n, e]]`.

- [ ] **Step 4: Run focused hook tests and commit**

  Run: `cd frontend && npm test -- useLeafletMap.test.tsx useZoneDensityLayer.test.tsx useAnchorLayer.test.tsx useRestrictionLayer.test.tsx`

  Expected: PASS.

  ```bash
  git add frontend/src/components/map/MapView.tsx \
    frontend/src/components/map/useLeafletMap.ts \
    frontend/src/components/map/useZoneDensityLayer.ts \
    frontend/src/components/map/useAnchorLayer.ts \
    frontend/src/components/map/useRestrictionLayer.ts \
    frontend/src/components/map/useLeafletMap.test.tsx \
    frontend/src/components/map/useZoneDensityLayer.test.tsx \
    frontend/src/components/map/useAnchorLayer.test.tsx \
    frontend/src/components/map/useRestrictionLayer.test.tsx
  git commit -m "feat: reload map layers by selected country"
  ```

### Task 5: Add the localized selector and application state

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/MapChrome.tsx`
- Modify: `frontend/src/components/FloatingNav.tsx`
- Modify: `frontend/src/components/NavMenu.tsx`
- Modify: `frontend/src/lib/i18n/strings.ts`
- Test: `frontend/src/App.test.tsx`
- Test: `frontend/src/components/NavMenu.test.tsx`
- Test: `frontend/src/lib/i18n/i18n.test.tsx`

**Interfaces:**

- Consumes: `fetchCountries`, `CountryEntry`, and country-aware `MapView` from
  Tasks 3–4.
- Produces: `selectedCountry: string`, `countryBounds`, and menu props
  `countries`, `country`, and `onCountryChange`.

- [ ] **Step 1: Write failing UI tests**

  Mock `/countries` with Spain and France. Assert the menu exposes a combobox
  labelled with the new translated `country` string, initially selects Spain,
  and lists both entries. Select France and assert:

  ```typescript
  expect(fetch).toHaveBeenCalledWith("/restrictions/layers?country=france", expect.anything());
  expect(screen.getByRole("checkbox", { name: /zepa/i })).not.toBeChecked();
  ```

  In the NavMenu test, verify country IDs are rendered as readable labels
  (`"Spain"`, `"France"`) rather than raw lowercase directory IDs. Add
  `country` to all three locale catalogs and let the existing parity test cover
  the key sets.

- [ ] **Step 2: Run the UI tests and confirm they fail because no country selector exists**

  Run: `cd frontend && npm test -- App.test.tsx NavMenu.test.tsx i18n.test.tsx`

  Expected: FAIL with no country combobox and missing country API requests.

- [ ] **Step 3: Implement catalog loading, selection reset, and menu control**

  In `App.tsx`, initialize `selectedCountry` to `"spain"`; load
  `fetchCountries` on mount; retain Spain when present and otherwise select the
  first catalog item; and derive `countryBounds` from the selected entry. Fetch
  restriction metadata whenever `selectedCountry` changes:

  ```typescript
  fetchRestrictionLayers(selectedCountry, controller.signal)
    .then(setRestrictionLayers)
  ```

  In the selection handler, call `setSelectedCountry(id)`,
  `setEnabledRestrictions([])`, and `setRestrictionLayers([])`. Pass country
  and bounds into `MapView`; thread selector props through MapChrome and
  FloatingNav to NavMenu. Render it with the project’s existing `Select`
  primitives above restriction-area mode. Use an ID-to-display helper with
  `Intl.DisplayNames` when available and title-cased ID fallback; do not add a
  hard-coded country catalog to the frontend.

- [ ] **Step 4: Run frontend regression tests and commit**

  Run: `cd frontend && npm test -- App.test.tsx NavMenu.test.tsx i18n.test.tsx`

  Expected: PASS.

  ```bash
  git add frontend/src/App.tsx frontend/src/components/MapChrome.tsx \
    frontend/src/components/FloatingNav.tsx frontend/src/components/NavMenu.tsx \
    frontend/src/lib/i18n/strings.ts frontend/src/App.test.tsx \
    frontend/src/components/NavMenu.test.tsx frontend/src/lib/i18n/i18n.test.tsx
  git commit -m "feat: add country selection to map menu"
  ```

### Task 6: Full verification

**Files:**

- Modify only if failures expose a defect in Tasks 1–5.

**Interfaces:**

- Consumes: complete backend and frontend country-selection implementation.
- Produces: verified lint, type, dead-code, backend-test, frontend-test, and
  production-build evidence.

- [ ] **Step 1: Run backend quality checks**

  Run: `just lint && just typecheck && just deadcode && just test`

  Expected: all commands exit 0.

- [ ] **Step 2: Run frontend quality checks and production build**

  Run: `just test-web && just build-web`

  Expected: Vitest passes and Vite completes without TypeScript errors.

- [ ] **Step 3: Inspect final diff**

  Run: `git diff --check HEAD~5..HEAD && git status --short`

  Expected: no whitespace errors and no unintended files. Report any remaining
  unexpected changes instead of staging them.
