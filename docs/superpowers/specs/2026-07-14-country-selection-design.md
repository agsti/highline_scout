# Country Selection Design

## Goal

Let a visitor choose which precomputed country to explore. Every map-backed
request must use that country only, and selecting a country must frame its
available data coverage on the map.

## Country catalog

The server will derive the catalog once while it builds its existing, static
region index from `data/<country>/<region>/grid.json`. No separate catalog
file, ETL command, or Just recipe is needed: the grid files are already the
authoritative data and the calculation only transforms each grid's four
corners to WGS84.

Each catalog entry has:

- `id`: the country directory name.
- `bounds_lonlat`: the union `[west, south, east, north]` of its indexed
  region extents.
- `center_lonlat`: the midpoint of those bounds.

The catalog describes available precomputed coverage, not the legal boundary
of a country. It is therefore correct even when only part of a country has
been processed.

## API

Add a country-catalog response backed by the cached index. Retain the current
`country` query parameter (defaulting to Spain for compatibility) on
`/regions`, `/zones`, `/anchors`, `/density`, and `/restrictions`, and add it
to `/restrictions/layers` so all map-data APIs share the same contract.

The frontend API client will accept a required `country` argument for all map
data calls and serialize it into each request. Country-specific restriction
metadata remains allowed to fall back to the shared layer definitions when a
country has no stored restriction files.

## Frontend behavior

Place a localized country selector in the existing map menu. It receives the
catalog from the API, initially selects `spain` when available, and displays
the catalog IDs as human-friendly labels. When the visitor selects a country,
the app:

1. Stores the selected ID as the single country state.
2. Clears enabled restriction layers and fetches metadata for the new country.
3. Fits the Leaflet map to that catalog entry's `bounds_lonlat` (using its
   center only as fallback if bounds cannot be fit).
4. Lets the existing viewport-driven hooks reload zones, density, anchors, and
   restrictions using the new ID. Their effect cleanup aborts requests from
   the previous country, preventing stale data from appearing.

The current filter values and anchor visibility remain unchanged across a
country change. The map viewport changes, which naturally triggers a fresh
load for the chosen country.

## Error handling

If the catalog cannot be loaded, the application keeps Spain selected and
reports the normal API error. A catalog with no countries leaves the selector
a disabled control and the map continues to render without result layers.

## Tests

Backend tests cover country bounds and centers derived from multiple region
grids, plus catalog/API country scoping. Frontend tests cover the country
query parameter on zones, density, anchors, restrictions, and restriction
metadata; selector rendering; country-change state reset; and fitting the map
to the selected catalog bounds.
