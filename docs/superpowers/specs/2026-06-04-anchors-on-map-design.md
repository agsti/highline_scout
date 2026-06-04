# Showing anchors on the map — design

Date: 2026-06-04

## Goal

Display detected anchors (cliff-edge rig points) on the web map as a **scouting
aid**. Each anchor shows as a point plus shaded **wedges** indicating which
compass directions the ground drops away. The layer is toggleable and **on by
default**. Wedges render when the view is sparse; plain dots render when it is
dense, to keep the map responsive.

Today the UI only shows highline *candidates* (lines between anchor pairs from
`/candidates`). The underlying anchors (stored per region in
`anchors.parquet`, each an `Anchor(x, y, elev, sectors)`) are never displayed
and there is no endpoint that serves them.

## Approach

Add a dedicated `GET /anchors` endpoint that returns anchor **points** with
their sector data as properties, and compute the **wedge geometry on the
frontend**.

Rationale:
- Payload stays tiny — center coordinate + sector angles, not polygon rings.
- Mirrors the existing `/candidates` bbox request pattern.
- The dots-vs-wedges decision lives on the frontend, where zoom and feature
  count are known.

Rejected alternative: building wedge polygons on the backend — larger payloads,
and the backend doesn't know the render mode.

## Components

### 1. `anchors.to_geojson(anchors) -> dict`

Pure function in `highliner/anchors.py`. Serializes a list of `Anchor` to a
GeoJSON `FeatureCollection` of `Point` features. Each feature:

- `geometry`: `Point` at `geo.to_lonlat(a.x, a.y)`.
- `properties`: `{ "elev": <float>, "sectors": [[start, end, drop], ...] }`
  (sectors copied from `a.sectors`).

Unit-testable in isolation.

### 2. `GET /anchors` endpoint

In `highliner/api.py`. Parameters `region`, `bbox`/`bbox_lonlat`, parsed
exactly like `/candidates` (reuse the same UTM conversion logic). Steps:

1. Resolve region via the existing `_region(region)` cache (anchors already
   loaded there).
2. Filter anchors whose `(x, y)` falls within the bbox.
3. Safety cap: if the in-view count exceeds `config.MAX_ANCHORS_IN_VIEW`
   (e.g. 20000, matching the candidates guard), raise `413 "zoom in"`.
4. Return `anchors.to_geojson(in_view)`.

### 3. Frontend anchor layer (`web/app.js`)

A Leaflet `LayerGroup` for anchors, added to the map by default.

- Triggered on `moveend`, region change, and toggle-on. Skips its fetch when
  the toggle is off.
- Fetches `/anchors?region&bbox_lonlat=...`.
- Render mode by feature count:
  - **≤ detail limit** (e.g. 400 features): a small center `circleMarker` plus
    one polygon **wedge per sector** — apex at the anchor, arc at a fixed
    ~30 m radius spanning the sector's start→end bearing (clockwise from north,
    matching `geo.bearing`). Wedge vertices computed on the frontend via a
    destination-point helper (meters → lat/lng).
  - **> detail limit**: plain canvas `circleMarker` dots (cheap, no wedges).
- Popup (both modes): elevation + sectors text.
- Color distinct from the pink candidates (`#e6005c`) — e.g. teal `#1f9e8f`.

### 4. `web/index.html`

A "Show anchors" checkbox (checked by default) in the control panel.

## Data flow

`moveend` / region-change → fetch `/candidates` **and** `/anchors` for the
current bbox → clear and redraw each layer independently. The toggle adds or
removes the anchor layer and skips its fetch while off.

## Error handling

- `413` from `/anchors` → status text "zoom in to see anchors"; the anchor
  layer is cleared. Candidates are unaffected.
- Any fetch error → small status note; does not break the candidates flow.

## Testing

- **Unit**: `anchors.to_geojson` — point coordinates and sectors round-trip.
- **API** (`tests/test_api.py`): `/anchors` returns points within the bbox,
  filters out-of-view anchors, and returns `413` past the cap.
- **Frontend**: the repo has no JS test harness, so the wedge/dots rendering
  and the toggle are verified manually in the running app.

## Out of scope

- Clustering / server-side decimation beyond the simple cap.
- Editing or adding anchors from the UI.
- Per-sector filtering controls.
