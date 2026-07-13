# Restriction-area display mode

## Goal

Let users choose whether enabled protected-area layers are informational map
overlays or client-side exclusion areas for scout results.

## User interface

The top-right navigation menu will contain a localized setting named
"Restriction areas". It uses a two-option select:

- **Informative** (default): enabled restriction layers are drawn on the map;
  zones and anchors remain unchanged.
- **Exclude results**: enabled restriction layers remain drawn and additionally
  exclude matching results from the map.

The existing restriction-layer controls continue to choose the enabled layers.
They do not contain the mode setting. The enabled layers define the scope of
exclusion when the mode is `Exclude results`.

## Filtering behavior

All filtering remains in the browser. No API endpoint, offline data, or server
filter changes are required.

- A zone is hidden if its rendered polygon overlaps at least one currently
  loaded feature from an enabled restriction layer.
- An anchor is hidden if its point is inside at least one currently loaded
  feature from an enabled restriction layer.
- With no enabled layers, `Exclude results` has no effect.
- Switching mode or changing enabled layers immediately re-renders results
  using the same client-side geometry data.

Restriction geometry is fetched for the current viewport. Therefore exclusion
is exact for the visible map area and is recomputed as the viewport changes.

## Density-mode boundary

At low zoom the application receives aggregate density cells, not individual
zone geometries. The setting will not alter density cells. Once zoomed in far
enough to render zones, exclusion applies normally. This limit is explicit in
the implementation and test coverage rather than approximating an exclusion
from density data.

## Implementation boundaries

The app will own the new `restrictionAreaMode` state and pass it to the
top-right menu and the map layers. Geometry predicates will be isolated in a
small frontend helper so zone-overlap and anchor-containment behavior is
testable independent of Leaflet request/render lifecycles. The zone and anchor
hooks will retain the latest restriction feature collection and render filtered
features whenever source results, enabled layers, mode, or viewport geometry
changes.

All new UI text will be added to the Catalan, Spanish, and English catalogs.

## Tests

- Top-right menu renders the localized setting and changes the selected mode.
- Informative mode preserves zones and anchors.
- Exclude-results mode removes a zone overlapping an enabled restriction and
  an anchor contained in one.
- The mode has no effect without enabled layers and does not filter density
  data.
- Existing localization parity and restriction-overlay tests continue to pass.
