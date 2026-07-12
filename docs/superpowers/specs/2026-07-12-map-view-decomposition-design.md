# Map View Decomposition Design

## Goal

Split the Leaflet map feature into focused, independently testable modules while preserving all existing map behavior, API requests, analytics, localization, and public `MapView` props.

## Scope

This work is limited to the map feature. It does not add React-Leaflet, a query/cache library, a map context/provider, API-contract generation, or changes to the visual UI.

## Architecture

`MapView` remains the public composition component. It owns the Leaflet element ref, renders the loading indicator, context menu, and zoom controls, and connects the existing public callbacks to extracted hooks.

`useLeafletMap` creates and disposes the Leaflet map, installs the base tile and restriction pane, and emits map movement events. The hook exposes a stable map ref plus a monotonically increasing viewport revision for consumers that need to reload after the map settles.

Three overlay hooks own their complete request and rendering lifecycles:

- `useZoneDensityLayer` chooses zones or density from the current zoom, cancels superseded requests, keeps the existing zone deduplication behavior, drives the shared loading state, and reports the existing status/error/density callbacks.
- `useAnchorLayer` fetches and renders anchors only when enabled and at the existing minimum zoom.
- `useRestrictionLayer` fetches and renders selected restriction layers, including the existing 413 zoom guidance.

`MapContextMenu` is a presentational React component that owns desktop/mobile actions and the document-level dismissal listeners. Link-copying remains a small exported helper so it can retain its direct unit tests.

`leafletLayers.ts` remains the only module that turns GeoJSON into styled Leaflet layers and markers. It is not moved or behaviorally changed by this refactor.

## Data Flow

```text
Leaflet map moveend
  -> useLeafletMap publishes map + viewport revision
  -> overlay hooks read bounds and zoom
  -> typed api.ts requests, each protected by AbortController
  -> leafletLayers renders results into its owned Leaflet layer
  -> hooks notify existing MapView callbacks for loading, status, errors, density mode
```

Changing language rebuilds the zone and density Leaflet layers with localized popup/tooltip content without re-fetching their data. Anchor and restriction fetches retain their current behavior.

## Public Interfaces and Compatibility

- `MapViewProps` remains unchanged. Existing callers and tests continue to use `onViewportChange`, optional status callbacks, `onError`, `onDensityModeChange`, and existing filter/overlay props.
- API request shapes, map zoom thresholds, zone deduplication keys, analytics event names/properties, URL view parsing, and translated strings remain unchanged.
- The map still uses imperative Leaflet. No Leaflet instance crosses the feature boundary into `App` or unrelated UI components.

## Error Handling and Request Safety

Every hook creates an `AbortController` for its current request and aborts it during cleanup. Zone/density loading keeps its request-id guard so an older request cannot clear the current spinner or overwrite newer data. Aborted requests are silent. Existing 413 handling remains informational zoom guidance; all other failures become localized errors through the existing callbacks.

## Testing

- Preserve the current `MapView` behavior tests by adapting mocks only where module extraction requires it.
- Add focused tests for each extracted hook/module's observable behavior: viewport events, zones-versus-density selection and cancellation, anchor zoom/enable gates, restriction selection/413 handling, and context-menu dismissal/actions.
- Keep pure rendering/analytics tests in `leafletLayers.analytics.test.ts` and popup formatting tests in `popups.test.ts`.
- Run the frontend Vitest suite and production build after every implementation task.
