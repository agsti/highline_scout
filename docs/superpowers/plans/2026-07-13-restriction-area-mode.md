# Restriction-area mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users select a top-right-menu mode that treats enabled restriction overlays as information or client-side exclusion areas for zones and anchors.

**Architecture:** `App` owns a `RestrictionAreaMode` value and supplies it through `MapChrome`/`FloatingNav` to `NavMenu`, and to `MapView`. `useRestrictionLayer` publishes its current GeoJSON collection to `MapView`; zone and anchor hooks retain their unfiltered API responses and rerender from a shared pure geometry filter whenever the mode or restriction collection changes.

**Tech Stack:** React 18, TypeScript strict mode, Vitest, Testing Library, Leaflet, existing Radix Select primitives; no new dependency.

## Global Constraints

- Add all UI text to Catalan, Spanish, and English `STRINGS` catalogs.
- Default mode is `informative`; mode state is session-only and is not persisted or sent to the API.
- In `exclude` mode, only currently enabled and currently fetched restriction features are considered.
- Hide a zone when its polygon overlaps a restriction polygon; hide an anchor when its point is within a restriction polygon.
- Keep density cells unfiltered at low zoom because they do not contain source-zone geometry.
- Preserve the current restriction overlay rendering in both modes.
- Do not modify backend endpoints, ETL output, or density responses.

---

## File structure

- `frontend/src/lib/restriction-filter.ts` — pure GeoJSON containment/overlap predicates and collection filters.
- `frontend/src/lib/restriction-filter.test.ts` — geometry behavior independent of Leaflet.
- `frontend/src/types/highliner.ts` — shared `RestrictionAreaMode` type.
- `frontend/src/lib/i18n/strings.ts` — localized menu label and two option labels.
- `frontend/src/components/NavMenu.tsx` — top-right mode select.
- `frontend/src/components/NavMenu.test.tsx` — menu interaction and localized select rendering.
- `frontend/src/App.tsx` — source of truth for mode and map/chrome wiring.
- `frontend/src/components/MapChrome.tsx` / `frontend/src/components/FloatingNav.tsx` — pass mode props to `NavMenu`.
- `frontend/src/components/map/MapView.tsx` — retain fetched restriction features and pass them to result hooks.
- `frontend/src/components/map/useRestrictionLayer.ts` — publish each successful, cleared, and failed restriction collection to `MapView`.
- `frontend/src/components/map/useZoneDensityLayer.ts` — cache raw zones and render their filtered collection; do not filter density.
- `frontend/src/components/map/useAnchorLayer.ts` — cache raw anchors and render their filtered collection.
- Existing hook tests — assert rerendering with exclusion geometry removes matching results.

### Task 1: Add mode type, translations, and the top-right menu control

**Files:**
- Modify: `frontend/src/types/highliner.ts`
- Modify: `frontend/src/lib/i18n/strings.ts`
- Modify: `frontend/src/components/NavMenu.tsx`
- Modify: `frontend/src/components/FloatingNav.tsx`
- Modify: `frontend/src/components/MapChrome.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/components/NavMenu.test.tsx`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces `type RestrictionAreaMode = "informative" | "exclude"`.
- `NavMenu` consumes `restrictionAreaMode: RestrictionAreaMode` and `onRestrictionAreaModeChange: (mode: RestrictionAreaMode) => void`.
- `MapView` will consume the same mode in Task 3.

- [ ] **Step 1: Write failing menu and app wiring tests**

  In `NavMenu.test.tsx`, make the harness own `const [mode, setMode] = useState<RestrictionAreaMode>("informative")`, then assert opening the English menu exposes a label `Restriction areas` and a select value `Informative`. Select `Exclude results` and assert the trigger now reads that value. In `App.test.tsx`, extend the mocked `MapView` props and output with `restrictionAreaMode`, then use the real top-right menu through `MapChrome`/`FloatingNav` (or only mock the map) to assert App passes `exclude` after the selection.

  ```tsx
  expect(screen.getByText("Restriction areas")).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Restriction areas" })).toHaveTextContent("Informative");
  await user.click(screen.getByRole("combobox", { name: "Restriction areas" }));
  await user.click(screen.getByRole("option", { name: "Exclude results" }));
  expect(screen.getByRole("combobox", { name: "Restriction areas" })).toHaveTextContent("Exclude results");
  ```

- [ ] **Step 2: Run the focused tests and verify they fail for missing props/text**

  Run: `npm test -- --run frontend/src/components/NavMenu.test.tsx frontend/src/App.test.tsx`

  Expected: FAIL because `Restriction areas` and `restrictionAreaMode` do not yet exist.

- [ ] **Step 3: Implement the minimal state and select plumbing**

  Add this type after the restriction collection aliases:

  ```ts
  export type RestrictionAreaMode = "informative" | "exclude";
  ```

  Add matching `restrictionAreas`, `restrictionAreasInformative`, and `restrictionAreasExclude` keys to every `STRINGS` catalog (Catalan: `Àrees restringides`, `Informatiu`, `Exclou resultats`; Spanish: `Áreas restringidas`, `Informativo`, `Excluir resultados`; English as above).

  In `App`, initialize `const [restrictionAreaMode, setRestrictionAreaMode] = useState<RestrictionAreaMode>("informative")`; pass it to both `MapView` and `MapChrome`. Extend `MapChrome` and `FloatingNav` prop interfaces and forwarding calls. In `NavMenu`, import the type and existing `Select`, `SelectContent`, `SelectItem`, `SelectTrigger`, and `SelectValue` components; render a labeled select in its own border-top menu section above the language section:

  ```tsx
  <div className="border-t border-hairline px-3.5 py-2.5">
    <label htmlFor="restriction-area-mode" className="text-[11px] font-[650] uppercase tracking-[0.04em] text-muted-foreground">
      {t("restrictionAreas")}
    </label>
    <Select value={restrictionAreaMode} onValueChange={onRestrictionAreaModeChange}>
      <SelectTrigger id="restriction-area-mode" aria-label={t("restrictionAreas")} className="mt-1.5 h-8">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="informative">{t("restrictionAreasInformative")}</SelectItem>
        <SelectItem value="exclude">{t("restrictionAreasExclude")}</SelectItem>
      </SelectContent>
    </Select>
  </div>
  ```

- [ ] **Step 4: Run focused tests and typecheck**

  Run: `npm test -- --run frontend/src/components/NavMenu.test.tsx frontend/src/App.test.tsx && npm run build`

  Expected: both test files pass and Vite typecheck/build exits 0.

- [ ] **Step 5: Commit the UI state task**

  ```bash
  git add frontend/src/types/highliner.ts frontend/src/lib/i18n/strings.ts frontend/src/components/NavMenu.tsx frontend/src/components/NavMenu.test.tsx frontend/src/components/FloatingNav.tsx frontend/src/components/MapChrome.tsx frontend/src/App.tsx frontend/src/App.test.tsx
  git commit -m "feat: add restriction area mode menu"
  ```

### Task 2: Implement and prove the client-side geometry filter

**Files:**
- Create: `frontend/src/lib/restriction-filter.ts`
- Test: `frontend/src/lib/restriction-filter.test.ts`

**Interfaces:**
- Consumes `AnchorFeatureCollection`, `RestrictionFeatureCollection`, and `ZoneFeatureCollection`.
- Produces `filterAnchorsByRestrictions(anchors, restrictions): AnchorFeatureCollection` and `filterZonesByRestrictions(zones, restrictions): ZoneFeatureCollection`.

- [ ] **Step 1: Write failing pure-geometry tests**

  Create literal square GeoJSON features. Assert an anchor in a restriction is removed while one outside remains; assert a zone with a crossing edge is removed; assert a zone wholly containing a restriction is removed; assert disjoint geometry remains. Include a polygon with a hole and assert a point in the hole is not treated as restricted.

  ```ts
  expect(filterAnchorsByRestrictions(anchors, restrictions).features).toEqual([outsideAnchor]);
  expect(filterZonesByRestrictions(zones, restrictions).features).toEqual([disjointZone]);
  ```

- [ ] **Step 2: Run the unit test and verify it fails because the module is absent**

  Run: `npm test -- --run frontend/src/lib/restriction-filter.test.ts`

  Expected: FAIL with module-not-found.

- [ ] **Step 3: Implement the smallest dependency-free geometry module**

  Keep coordinates in `[longitude, latitude]` order. Export only the two collection filters. Internally implement:

  ```ts
  function pointInPolygon(point: Position, polygon: PolygonGeometry): boolean;
  function polygonsOverlap(first: PolygonGeometry, second: PolygonGeometry): boolean;
  function segmentsIntersect(a: Position, b: Position, c: Position, d: Position): boolean;
  ```

  `pointInPolygon` must use ray casting against the exterior ring and return false for a point in any subsequent hole ring. `polygonsOverlap` must return true when any exterior-ring segment pair intersects or when an exterior-ring vertex of either polygon is in the other polygon. Each filter returns the original collection shape with only features for which no restriction matches. Do not mutate input collections.

- [ ] **Step 4: Run the geometry unit test**

  Run: `npm test -- --run frontend/src/lib/restriction-filter.test.ts`

  Expected: all containment, edge-crossing, enclosure, disjoint, and hole tests pass.

- [ ] **Step 5: Commit the geometry task**

  ```bash
  git add frontend/src/lib/restriction-filter.ts frontend/src/lib/restriction-filter.test.ts
  git commit -m "feat: filter results against restriction geometry"
  ```

### Task 3: Publish fetched restrictions and rerender zones without filtering density

**Files:**
- Modify: `frontend/src/components/map/useRestrictionLayer.ts`
- Modify: `frontend/src/components/map/MapView.tsx`
- Modify: `frontend/src/components/map/useZoneDensityLayer.ts`
- Test: `frontend/src/components/map/useRestrictionLayer.test.tsx`
- Test: `frontend/src/components/map/useZoneDensityLayer.test.tsx`

**Interfaces:**
- `useRestrictionLayer` gains `onFeaturesChange?: (features: RestrictionFeatureCollection) => void`.
- `useZoneDensityLayer` gains `restrictionAreaMode: RestrictionAreaMode` and `restrictionFeatures: RestrictionFeatureCollection`.

- [ ] **Step 1: Write failing hook tests**

  In the restriction hook test, supply `onFeaturesChange` and assert a successful fetch publishes its complete collection; assert zero enabled layers publishes `{ type: "FeatureCollection", features: [] }`. In the zone hook test, add mode/features props to the harness, resolve one overlapping and one disjoint zone, rerender with `exclude` and the square restriction collection, then assert the last `zoneLayer.addData` call contains only the disjoint zone. Add a density-zoom test that rerenders the same exclusion props and asserts `densityLayer.addData` still receives the original density collection.

- [ ] **Step 2: Run hook tests and verify they fail due to missing callbacks/filter props**

  Run: `npm test -- --run frontend/src/components/map/useRestrictionLayer.test.tsx frontend/src/components/map/useZoneDensityLayer.test.tsx`

  Expected: FAIL because the new callbacks and filtering props do not exist.

- [ ] **Step 3: Publish restriction data and apply zone rendering filters**

  In `useRestrictionLayer`, invoke `onFeaturesChange(emptyCollection)` whenever selection is empty or a request fails, and invoke it with `fc` immediately before adding `fc` to the Leaflet overlay after a successful current request. In `MapView`, hold `restrictionFeatures` in state initialized to the empty collection, pass its setter as the callback, then pass the mode and collection to `useZoneDensityLayer`.

  In `useZoneDensityLayer`, retain raw deduplicated zone features in `shownZoneFeaturesRef`. Extract a local `renderZones()` that clears `zoneLayerRef.current`, builds `{ type: "FeatureCollection", features: shownZoneFeaturesRef.current }`, applies `filterZonesByRestrictions` only when `restrictionAreaMode === "exclude"`, and adds the result. Call it after a zones response, after recreating a zone layer, and from an effect keyed by `restrictionAreaMode` and `restrictionFeatures`. Leave the density branch untouched except for clearing zones as it already does.

- [ ] **Step 4: Run hook tests and build**

  Run: `npm test -- --run frontend/src/components/map/useRestrictionLayer.test.tsx frontend/src/components/map/useZoneDensityLayer.test.tsx && npm run build`

  Expected: both hook suites pass and build exits 0.

- [ ] **Step 5: Commit the zone integration task**

  ```bash
  git add frontend/src/components/map/useRestrictionLayer.ts frontend/src/components/map/useRestrictionLayer.test.tsx frontend/src/components/map/MapView.tsx frontend/src/components/map/useZoneDensityLayer.ts frontend/src/components/map/useZoneDensityLayer.test.tsx
  git commit -m "feat: exclude restricted zones on the map"
  ```

### Task 4: Rerender anchors using the same restriction data

**Files:**
- Modify: `frontend/src/components/map/MapView.tsx`
- Modify: `frontend/src/components/map/useAnchorLayer.ts`
- Test: `frontend/src/components/map/useAnchorLayer.test.tsx`

**Interfaces:**
- `useAnchorLayer` gains `restrictionAreaMode: RestrictionAreaMode` and `restrictionFeatures: RestrictionFeatureCollection`.

- [ ] **Step 1: Write a failing anchor exclusion test**

  Make `fetchAnchors` resolve one point inside the square restriction and one outside. Render in `informative` mode and assert mocked `renderAnchors` receives both. Rerender with `exclude` and the restriction collection; assert its most recent call receives only the outside point. Add a test that `exclude` with an empty collection still renders both points.

- [ ] **Step 2: Run the anchor test and verify it fails for the missing filter props**

  Run: `npm test -- --run frontend/src/components/map/useAnchorLayer.test.tsx`

  Expected: FAIL because the hook does not accept or react to restriction mode/features.

- [ ] **Step 3: Cache source anchors and rerender their filtered collection**

  In `useAnchorLayer`, add `const shownAnchorsRef = useRef<AnchorFeatureCollection>({ type: "FeatureCollection", features: [] })`. After a successful request, assign the raw collection then call a local `renderVisibleAnchors()` that calls `renderAnchors(layer, mode === "exclude" ? filterAnchorsByRestrictions(raw, restrictionFeatures) : raw)`. Add a separate effect keyed by mode and restriction features to call the same function without refetching. Clear the ref and Leaflet layer when anchors are disabled, below minimum zoom, or their request fails. Pass both values from `MapView`.

- [ ] **Step 4: Run the focused anchor test and build**

  Run: `npm test -- --run frontend/src/components/map/useAnchorLayer.test.tsx && npm run build`

  Expected: the test file passes and build exits 0.

- [ ] **Step 5: Commit the anchor integration task**

  ```bash
  git add frontend/src/components/map/MapView.tsx frontend/src/components/map/useAnchorLayer.ts frontend/src/components/map/useAnchorLayer.test.tsx
  git commit -m "feat: exclude restricted anchors on the map"
  ```

### Task 5: Run the complete frontend verification suite

**Files:**
- Verify only; do not alter unrelated files.

- [ ] **Step 1: Run the frontend suite**

  Run: `npm test`

  Expected: all Vitest suites pass, including existing analytics, map, component, and i18n parity tests.

- [ ] **Step 2: Run the production build**

  Run: `npm run build`

  Expected: TypeScript project build and Vite production build exit 0.

- [ ] **Step 3: Review the final scoped diff**

  Run: `git diff --check HEAD~4..HEAD && git status --short`

  Expected: no whitespace errors; only the planned commits are new, with pre-existing unrelated changes left unmodified.

## Plan self-review

- **Spec coverage:** Tasks 1–4 cover the top-right localized mode control, default informative state, enabled-layer scope, client-only zone/anchor filtering, unchanged overlays, and unchanged density behavior. Task 5 verifies the full frontend boundary.
- **No placeholders:** all tasks name files, interfaces, test cases, concrete commands, expected outcomes, and commits.
- **Type consistency:** `RestrictionAreaMode`, `RestrictionFeatureCollection`, the geometry-filter function names, and hook prop names are defined once and reused consistently.

## Approved revision: three restriction-area modes

Replace the original two-mode implementation details with the following before
final verification:

- Change `RestrictionAreaMode` to `"informative" | "exclude-overlaps" |
  "exclude-inside"` and replace all `"exclude"` checks accordingly.
- Replace the English option copy with `Exclude overlaps` and add `Exclude
  inside`, with corresponding Catalan and Spanish translations.
- `filterZonesByRestrictions` must support both exclusion policies. In
  `exclude-overlaps`, retain the existing any-overlap predicate. In
  `exclude-inside`, remove a zone only if one restriction polygon contains
  every exterior-ring vertex of that zone and no zone edge crosses the
  restriction exterior or a hole boundary. Do not union restriction polygons.
- `filterAnchorsByRestrictions` applies identically in both exclusion modes:
  remove anchors whose point is in any enabled restriction polygon.
- Extend pure geometry tests with a partly overlapping zone (removed only by
  `exclude-overlaps`), a wholly contained zone (removed by both), and a zone
  split across two restriction polygons (retained by `exclude-inside`).
- Extend menu, zone, and anchor tests to verify all three choices and both
  exclusion behaviors. Update `MapView.test.tsx`'s pan assertion to expect the
  accumulated visible zone collection after redraw, not only the latest API
  page.
