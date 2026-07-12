# Map View Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose the imperative Leaflet map feature into focused lifecycle, overlay, and context-menu modules without changing map behavior or `MapView`’s public API.

**Architecture:** `MapView` remains the feature entry point and only composes hooks, map controls, and overlays. `useLeafletMap` owns map construction/events, three overlay hooks own their own request/render lifecycles, and `MapContextMenu` owns the responsive point-action UI. Existing `leafletLayers.ts`, `api.ts`, analytics events, and localization remain the shared behavior boundaries.

**Tech Stack:** React 18, TypeScript 5, Leaflet 1.9, Vite, Tailwind, Vitest, Testing Library.

## Global Constraints

- Work from `/home/gus/projects/highliner_finder`; frontend commands run from `frontend/`.
- Preserve the exact `MapViewProps` interface and all current public callbacks.
- Do not add React-Leaflet, a map provider/context, a query/cache library, API-contract generation, or UI changes.
- Preserve the existing API routes, request payloads, zoom constants, zone deduplication, localized text, URL parsing, and PostHog event names/properties.
- Every request uses `AbortController`; aborted requests are silent. The zones/density request-id guard must continue preventing stale responses from changing the active spinner or layers.
- `leafletLayers.ts` remains the single Leaflet GeoJSON/marker renderer. Do not duplicate style, popup, tooltip, or analytics logic in hooks.
- Run `npm test` and `npm run build` from `frontend/` after each task. If bare `npm` is unavailable, use the Node 20 path documented in the repository's existing frontend plans.

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/src/components/map/MapView.tsx` | Compose extracted hooks; retain DOM container, loading indicator, zoom controls, and public props. |
| `frontend/src/components/map/useLeafletMap.ts` | Create/dispose the Leaflet map, base tiles/pane, and publish map movement revision. |
| `frontend/src/components/map/useZoneDensityLayer.ts` | Load, deduplicate, render, and report zones or density. |
| `frontend/src/components/map/useAnchorLayer.ts` | Load/render anchors when enabled at the supported zoom. |
| `frontend/src/components/map/useRestrictionLayer.ts` | Load/render enabled protected-area layers. |
| `frontend/src/components/map/MapContextMenu.tsx` | Render and dismiss the desktop/mobile point-action menu. |
| `frontend/src/components/map/*.test.tsx` | Focused hook/component tests; retain `MapView.test.tsx` as composition coverage. |

### Task 1: Extract Leaflet initialization and viewport lifecycle

**Files:**
- Create: `frontend/src/components/map/useLeafletMap.ts`
- Create: `frontend/src/components/map/useLeafletMap.test.tsx`
- Modify: `frontend/src/components/map/MapView.tsx:1-230`
- Modify: `frontend/src/components/map/MapView.test.tsx:1-385`

**Interfaces:**
- Consumes: `HTMLElement | null`, `MapViewState`, `onViewportChange?: (map: L.Map) => void`, and `onViewStateChange?: (view: MapViewState) => void`.
- Produces:

```ts
export interface LeafletMapState {
  mapRef: React.MutableRefObject<L.Map | null>;
  viewportRevision: number;
}

export function useLeafletMap(options: {
  element: HTMLElement | null;
  t: T;
  lang: Lang;
  onViewportChange: (map: L.Map) => void;
  onViewStateChange?: (view: MapViewState) => void;
  onMapSettled: (map: L.Map) => void;
  onContextMenu: (event: L.LeafletMouseEvent) => void;
}): LeafletMapState;
```

- Produces for later tasks: an initialized map ref and `viewportRevision`; it must not create overlays or fetch API data.

- [ ] **Step 1: Write failing lifecycle tests**

Create `useLeafletMap.test.tsx` with a small harness that renders a `<div ref>` and invokes the hook. Mock Leaflet using the existing `MapView.test.tsx` map fixture. Assert creation, initialization, movement, and disposal:

```tsx
it("creates the base map once, publishes the initial viewport, and disposes it", () => {
  const onViewportChange = vi.fn();
  const { unmount } = render(<Harness onViewportChange={onViewportChange} />);

  expect(leafletMocks.map).toHaveBeenCalledTimes(1);
  expect(onViewportChange).toHaveBeenCalledWith(expect.objectContaining({ getBounds: expect.any(Function) }));

  unmount();
  expect(leafletMocks.remove).toHaveBeenCalledTimes(1);
});

it("increments the viewport revision and publishes state after moveend", () => {
  render(<Harness onViewportChange={vi.fn()} />);
  act(() => leafletState.moveend?.());
  expect(screen.getByTestId("viewport-revision")).toHaveTextContent("1");
});
```

- [ ] **Step 2: Run the hook test and verify failure**

Run: `npm test -- src/components/map/useLeafletMap.test.tsx`

Expected: FAIL because `useLeafletMap` does not exist.

- [ ] **Step 3: Implement `useLeafletMap`**

Move `DEFAULT_VIEW`, initial URL view selection, tile layer/pane creation, and `map.remove()` cleanup out of `MapView`. The hook must use a ref for the Leaflet map and state only for `viewportRevision`. Overlay hooks create and remove their own Leaflet layers in later tasks.

Use this event body; it preserves the established event ordering:

```ts
map.on("moveend", () => {
  options.onViewportChange(map);
  const center = map.getCenter();
  options.onViewStateChange?.({ center: [center.lat, center.lng], zoom: map.getZoom() });
  options.onMapSettled(map);
  setViewportRevision((revision) => revision + 1);
});
```

Do not put localization or overlay rebuild behavior in this hook; that responsibility belongs to `useZoneDensityLayer`.

- [ ] **Step 4: Adapt `MapView` to use the lifecycle hook**

Replace its map construction effect with:

```tsx
const mapState = useLeafletMap({
  element: elRef.current,
  t,
  lang,
  onViewportChange,
  onViewStateChange,
  onMapSettled: (map) => {
    const center = map.getCenter();
    captureMapSettled(map.getZoom(), center.lat, center.lng);
  },
  onContextMenu: setContextMenuFromLeafletEvent,
});
```

Keep the DOM ref callback stable so a render does not recreate the map. Keep `MapView`'s resize invalidation effect unchanged.

- [ ] **Step 5: Run focused and existing composition tests**

Run: `npm test -- src/components/map/useLeafletMap.test.tsx src/components/map/MapView.test.tsx`

Expected: PASS. Existing zoom, URL view, move, map removal, and language-rebuild assertions still pass.

- [ ] **Step 6: Build and commit**

Run: `npm run build`

Expected: exit code 0.

```bash
git add frontend/src/components/map/useLeafletMap.ts frontend/src/components/map/useLeafletMap.test.tsx frontend/src/components/map/MapView.tsx frontend/src/components/map/MapView.test.tsx
git commit -m "refactor(web): extract leaflet map lifecycle"
```

### Task 2: Extract the zones and density overlay lifecycle

**Files:**
- Create: `frontend/src/components/map/useZoneDensityLayer.ts`
- Create: `frontend/src/components/map/useZoneDensityLayer.test.tsx`
- Modify: `frontend/src/components/map/MapView.tsx:220-305`
- Modify: `frontend/src/components/map/MapView.test.tsx:417-635`

**Interfaces:**
- Consumes: initialized `mapRef`, zone/density layer refs, `viewportRevision`, filters, `t`, `onMapStatus`, `onError`, and `onDensityModeChange`.
- Produces:

```ts
export function useZoneDensityLayer(options: {
  mapRef: React.MutableRefObject<L.Map | null>;
  viewportRevision: number;
  minLen: number;
  maxLen: number;
  minExposure: number;
  lang: Lang;
  t: T;
  onMapStatus?: (status: string) => void;
  onError?: (message: string) => void;
  onDensityModeChange?: (dense: boolean) => void;
}): { isLoading: boolean };
```

- Produces for later tasks: the only map-fetch loading state displayed by `MapView`.

- [ ] **Step 1: Write failing hook tests**

Test the hook with mock map/layer refs and the existing `api.ts` mock. Cover the observable contracts:

```tsx
it("loads density at the density zoom and clamps the density tile zoom", async () => {
  map.getZoom.mockReturnValue(DENSITY_MAX_ZOOM);
  render(<Harness />);
  await waitFor(() => expect(fetchDensity).toHaveBeenCalledWith(
    { z: DENSITY_TILE_MAX, bboxLonLat: "1,2,3,4" }, expect.any(AbortSignal),
  ));
});

it("loads and deduplicates zone features across viewport revisions", async () => {
  fetchZones
    .mockResolvedValueOnce(featureCollection([zoneA, zoneA]))
    .mockResolvedValueOnce(featureCollection([zoneA, zoneB]));
  const { rerender } = render(<Harness viewportRevision={0} />);
  await waitFor(() => expect(zoneLayer.addData).toHaveBeenCalledWith(featureCollection([zoneA])));
  rerender(<Harness viewportRevision={1} />);
  await waitFor(() => expect(zoneLayer.addData).toHaveBeenLastCalledWith(featureCollection([zoneB])));
});

it("keeps loading visible until the current request resolves", async () => {
  const first = deferred<ZoneFeatureCollection>();
  const second = deferred<ZoneFeatureCollection>();
  fetchZones.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
  const { rerender } = render(<Harness viewportRevision={0} />);
  rerender(<Harness viewportRevision={1} />);
  await act(async () => first.resolve(featureCollection([])));
  expect(screen.getByTestId("loading")).toHaveTextContent("true");
  await act(async () => second.resolve(featureCollection([])));
  await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
});
```

- [ ] **Step 2: Run the new test file and verify failure**

Run: `npm test -- src/components/map/useZoneDensityLayer.test.tsx`

Expected: FAIL because `useZoneDensityLayer` does not exist.

- [ ] **Step 3: Move the zone/density effect without altering semantics**

Move `requestIdRef`, `shownZoneKeysRef`, `shownZoneFeaturesRef`, `shownDensityRef`, `densitySortedRef`, status rendering, and the existing effect from `MapView` into the hook. The hook creates zone/density layers when `mapRef.current` becomes available; on language changes it recreates only those layers and repopulates them from stored features without fetching. Keep this stale-response guard exactly:

```ts
const requestId = (requestIdRef.current += 1);
const controller = new AbortController();
const fc = await fetchZones({ bboxLonLat, minLen, maxLen, minExposure }, controller.signal);
if (requestId !== requestIdRef.current) return;
zoneLayerRef.current?.addData(fc);
finally {
  if (requestId === requestIdRef.current) setIsLoading(false);
}
```

On filter changes, clear zones and reset the dedupe set before the next zone request. Density mode clears zones; zone mode clears density. Preserve the existing `ApiError` 413 message and use `tRef` or an equivalent current-translation ref for asynchronous errors.

- [ ] **Step 4: Make `MapView` consume the hook result**

Replace the in-component zones/density effect and related refs with:

```tsx
const { isLoading } = useZoneDensityLayer({
  mapRef: mapState.mapRef,
  viewportRevision: mapState.viewportRevision,
  minLen,
  maxLen,
  minExposure,
  lang,
  t,
  onMapStatus,
  onError,
  onDensityModeChange,
});
```

- [ ] **Step 5: Run tests, build, and commit**

Run: `npm test -- src/components/map/useZoneDensityLayer.test.tsx src/components/map/MapView.test.tsx && npm run build`

Expected: all tests pass and build exits 0.

```bash
git add frontend/src/components/map/useZoneDensityLayer.ts frontend/src/components/map/useZoneDensityLayer.test.tsx frontend/src/components/map/MapView.tsx frontend/src/components/map/MapView.test.tsx
git commit -m "refactor(web): extract zones and density layer loading"
```

### Task 3: Extract anchors and restrictions overlays

**Files:**
- Create: `frontend/src/components/map/useAnchorLayer.ts`
- Create: `frontend/src/components/map/useAnchorLayer.test.tsx`
- Create: `frontend/src/components/map/useRestrictionLayer.ts`
- Create: `frontend/src/components/map/useRestrictionLayer.test.tsx`
- Modify: `frontend/src/components/map/MapView.tsx:306-367`
- Modify: `frontend/src/components/map/MapView.test.tsx:636-715`

**Interfaces:**
- Consumes: initialized `mapRef`, the matching Leaflet layer ref, `viewportRevision`, current selection prop(s), `t`, status callback, and error callback.
- Produces:

```ts
export function useAnchorLayer(options: {
  mapRef: React.MutableRefObject<L.Map | null>;
  viewportRevision: number;
  showAnchors: boolean;
  t: T;
  onAnchorStatus?: (status: string) => void;
  onError?: (message: string) => void;
}): void;

export function useRestrictionLayer(options: {
  mapRef: React.MutableRefObject<L.Map | null>;
  viewportRevision: number;
  enabledRestrictions: string[];
  restrictionLayers: RestrictionLayerMeta[];
  t: T;
  onRestrictionStatus?: (status: string) => void;
  onError?: (message: string) => void;
}): void;
```

- [ ] **Step 1: Write failing anchor hook tests**

```tsx
it("clears anchors and skips the request when disabled", () => {
  render(<AnchorHarness showAnchors={false} />);
  expect(layer.clearLayers).toHaveBeenCalledTimes(1);
  expect(fetchAnchors).not.toHaveBeenCalled();
});

it("shows zoom guidance instead of requesting anchors below ANCHOR_MIN_ZOOM", () => {
  map.getZoom.mockReturnValue(ANCHOR_MIN_ZOOM - 1);
  render(<AnchorHarness showAnchors />);
  expect(fetchAnchors).not.toHaveBeenCalled();
  expect(onAnchorStatus).toHaveBeenCalledWith("amplia per veure ancoratges");
});
```

- [ ] **Step 2: Run anchor tests and verify failure**

Run: `npm test -- src/components/map/useAnchorLayer.test.tsx`

Expected: FAIL because `useAnchorLayer` does not exist.

- [ ] **Step 3: Implement `useAnchorLayer`**

Create one `L.layerGroup()` after `mapRef.current` is available, add it to the map, and remove it in the hook cleanup. Move the existing anchor effect verbatim in behavior: clear the layer and status when disabled, clear/show localized zoom guidance below `ANCHOR_MIN_ZOOM`, call `fetchAnchors({ bboxLonLat })`, render via `renderAnchors`, and report `anchorError` on non-abort failure.

- [ ] **Step 4: Write failing restriction hook tests**

```tsx
it("clears restrictions and skips the request when none are selected", () => {
  render(<RestrictionHarness enabledRestrictions={[]} />);
  expect(layer.clearLayers).toHaveBeenCalledTimes(1);
  expect(fetchRestrictions).not.toHaveBeenCalled();
});

it("turns a 413 response into localized zoom guidance", async () => {
  fetchRestrictions.mockRejectedValue(new ApiError(413, "too many"));
  render(<RestrictionHarness enabledRestrictions={["zepa"]} />);
  await waitFor(() => expect(onRestrictionStatus).toHaveBeenCalledWith("amplia per veure espais protegits"));
  expect(onError).not.toHaveBeenCalled();
});
```

- [ ] **Step 5: Run restriction tests and verify failure**

Run: `npm test -- src/components/map/useRestrictionLayer.test.tsx`

Expected: FAIL because `useRestrictionLayer` does not exist.

- [ ] **Step 6: Implement `useRestrictionLayer`**

Create one restrictions-pane `L.geoJSON` layer after `mapRef.current` is available, retain a metadata ref built from the current layer metadata, add it to the map, and remove it in hook cleanup. Move the existing restriction effect verbatim in behavior. It calls `fetchRestrictions({ bboxLonLat, layers: enabledRestrictions })`, replaces layer data on success, emits `protectedAreasCount`, emits `zoomInToSee(nounProtectedAreas)` for `ApiError(413, ...)`, and emits the standard localized `error` for any other non-abort failure.

- [ ] **Step 7: Compose both hooks in `MapView`**

```tsx
useAnchorLayer({
  mapRef: mapState.mapRef,
  viewportRevision: mapState.viewportRevision,
  showAnchors,
  t,
  onAnchorStatus,
  onError,
});
useRestrictionLayer({
  mapRef: mapState.mapRef,
  viewportRevision: mapState.viewportRevision,
  enabledRestrictions,
  restrictionLayers,
  t,
  onRestrictionStatus,
  onError,
});
```

- [ ] **Step 8: Run tests, build, and commit**

Run: `npm test -- src/components/map/useAnchorLayer.test.tsx src/components/map/useRestrictionLayer.test.tsx src/components/map/MapView.test.tsx && npm run build`

Expected: all tests pass and build exits 0.

```bash
git add frontend/src/components/map/useAnchorLayer.ts frontend/src/components/map/useAnchorLayer.test.tsx frontend/src/components/map/useRestrictionLayer.ts frontend/src/components/map/useRestrictionLayer.test.tsx frontend/src/components/map/MapView.tsx frontend/src/components/map/MapView.test.tsx
git commit -m "refactor(web): extract anchor and restriction overlays"
```

### Task 4: Extract and verify the context menu, then simplify `MapView`

**Files:**
- Create: `frontend/src/components/map/MapContextMenu.tsx`
- Create: `frontend/src/components/map/MapContextMenu.test.tsx`
- Modify: `frontend/src/components/map/MapView.tsx:38-172,386-472`
- Modify: `frontend/src/components/map/MapView.test.tsx:716-768`

**Interfaces:**
- Consumes: a nullable context point, `t`, `onDismiss`, and map pan callback.
- Produces:

```ts
export interface ContextMenuPoint {
  lat: number;
  lng: number;
  zoom: number;
  x: number;
  y: number;
}

export async function copyViewportLink(lat: number, lng: number, zoom: number, t: T): Promise<void>;

export function MapContextMenu(props: {
  point: ContextMenuPoint | null;
  t: T;
  onDismiss: () => void;
}): React.ReactElement | null;
```

- [ ] **Step 1: Write failing context-menu tests**

```tsx
it("dismisses an open menu when Escape is pressed", async () => {
  const onDismiss = vi.fn();
  render(<MapContextMenu point={POINT} t={t} onDismiss={onDismiss} />);
  await userEvent.setup().keyboard("{Escape}");
  expect(onDismiss).toHaveBeenCalledTimes(1);
});

it("uses clipboard text for the viewport URL and falls back to prompt", async () => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  await copyViewportLink(41.5, 1.9, 13, t);
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://example.com/?lat=41.50000&lng=1.90000&z=13");
});
```

Also preserve the existing desktop Google Maps href, desktop click-to-copy, mobile menu, mobile marker, outside-pointer dismissal, and `Escape` coverage from `MapView.test.tsx`.

- [ ] **Step 2: Run the menu test and verify failure**

Run: `npm test -- src/components/map/MapContextMenu.test.tsx`

Expected: FAIL because `MapContextMenu` does not exist.

- [ ] **Step 3: Move menu UI and dismissal behavior into `MapContextMenu`**

Move `ContextMenuState` (renamed to `ContextMenuPoint`), `contextMenuRootRef`, the `pointerdown`/`keydown` effect, `copyContextMenuLink`, Google Maps href, and both desktop/mobile markup into the new component. Keep these behaviors unchanged:

```tsx
if (!point) return null;

const href = `https://www.google.com/maps?q=${point.lat},${point.lng}`;

function onPointerDown(event: PointerEvent) {
  if (event.target instanceof Node && rootRef.current?.contains(event.target)) return;
  props.onDismiss();
}
```

Keep `copyViewportLink` exported from this module and have the action call it with `point.lat`, `point.lng`, and `point.zoom` before dismissal.

- [ ] **Step 4: Reduce `MapView` to composition**

`MapView` now holds only `contextMenu` state and the mobile-pan preservation ref. Its Leaflet context-menu event converts the Leaflet event into `ContextMenuPoint`; on a mobile viewport it calls `map.panTo([lat, lng], { animate: true })` and preserves the menu for that induced move. Render:

```tsx
<MapContextMenu
  point={contextMenu}
  t={t}
  onDismiss={() => setContextMenu(null)}
/>
```

It must still render the full-size map container, `isLoading` spinner, `ZoomControls`, and the invalidation-size effect. It must not import API functions or `leafletLayers` directly after this task.

- [ ] **Step 5: Run final focused verification**

Run: `npm test -- src/components/map/MapContextMenu.test.tsx src/components/map/MapView.test.tsx src/components/map/leafletLayers.analytics.test.ts src/components/map/popups.test.ts`

Expected: all map-focused tests pass.

- [ ] **Step 6: Run full verification and commit**

Run: `npm test && npm run build`

Expected: the full Vitest suite passes and Vite/TypeScript production build exits 0.

```bash
git add frontend/src/components/map/MapContextMenu.tsx frontend/src/components/map/MapContextMenu.test.tsx frontend/src/components/map/MapView.tsx frontend/src/components/map/MapView.test.tsx
git commit -m "refactor(web): separate map context menu"
```

---

## Final Verification

- [ ] Run the browser app with `npm run dev` and verify high zoom loads zones, low zoom loads density, panning accumulates zones without duplicates, applying filters resets zones, anchors respect the zoom gate, and each restriction selection loads its overlay.
- [ ] Change language after zone and density data is visible; confirm popup/tooltip copy updates without another zones/density request.
- [ ] Check desktop right-click and mobile long-press context menus: Google Maps link, copy link, outside click, Escape, and mobile pan behavior remain intact.
- [ ] Confirm `MapView.tsx` contains no direct `fetchZones`, `fetchDensity`, `fetchAnchors`, `fetchRestrictions`, `createZoneLayer`, `createDensityLayer`, `renderAnchors`, or `createRestrictionLayer` imports.
