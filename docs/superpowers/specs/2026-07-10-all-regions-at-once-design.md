# All Regions At Once — Seamless Panning Design

**Date:** 2026-07-10
**Status:** Approved (design)

## Problem

The app is single-region. The user picks a region from a dropdown; the map flies
to it, and every data request (`/zones`, `/anchors`, `/density`) carries
`region=NAME`, which selects a `data/<region>/` partition. With ~20 Spanish
autonomous communities now precomputed, panning across a region border requires
manually switching the dropdown, and there is no way to just explore the map
continuously.

## Goal

**Seamless panning.** Remove the region concept from the UI. As the user pans and
zooms, the map auto-loads zones/anchors/density from whatever region partition(s)
overlap the current viewport. Crossing a region border "just works." Zoomed-in
behavior is otherwise unchanged.

Non-goal: a country-wide aggregated overview / national heatmap. Zoomed-out
behavior keeps using the existing per-region density pyramids, concatenated.

## Approach

### Backend — resolve regions from the viewport

Make `region` an **optional** query param on `/zones`, `/anchors`, `/density`.

- **`region` provided** → current behavior, restricted to that one region
  (kept for back-compat and debugging; existing tests stay green).
- **`region` omitted** → resolve which regions overlap the viewport and merge
  their results.

**Region index (cached).** Build a small in-memory index once per process, lazily
on first use, stored on `app.state`: for each `data/<region>/` containing a
`grid.json`, record `(name, region_dir, lonlat_bounds, grid)`. Reuses the
`_bounds_from_grid` logic currently in `router/regions.py` (factor it into a
shared helper). The precomputed data is static, so the index is never
invalidated.

**Per-request flow (region omitted):**
1. Parse the viewport as lon/lat (`parse_bbox_lonlat`).
2. Intersect it against each region's `lonlat_bounds` → the (usually 1–3)
   overlapping regions.
3. For each overlapping region: convert the viewport into *that region's* CRS
   (`grid.crs`), read its partitions, serialize features back to lon/lat using
   its CRS.
4. Concatenate features across regions into one FeatureCollection.

Because every response is already WGS84 GeoJSON, the fact that regions live in
different UTM zones (mainland zones 29/30/31; Canarias on its own datum) is
invisible to the client — each region converts using its own `grid.crs`.

**Shared helper.** Add a resolver (e.g. `router/deps.py` or a small service) that,
given `data_dir` + viewport lon/lat, yields the overlapping
`(region_dir, grid)` pairs from the cached index. Each router iterates it and
concatenates. This keeps `zones.py` / `anchors.py` / `density.py` thin.

**Rejected alternatives:**
- *Scan every `grid.json` per request* — re-reads ~20 files each time for no
  benefit; the cached index is barely more code.
- *Merge all regions into one unified precomputed store* — impossible to do
  cleanly: Spain + Canarias span multiple UTM zones/datums with no single
  sensible projected CRS.

### Frontend — remove the region concept

- Delete the region `<Select>` from `FilterControls`; remove `region`/`regions`
  state from `App.tsx`.
- Drop the `fetchRegions` call and the region-fit `useEffect` in `MapView`
  (the one that `fitBounds` to `selected.bounds_lonlat`). Initial view stays
  `DEFAULT_VIEW` or the URL's `?lat&lng&z`.
- Remove `region` from `fetchZones` / `fetchAnchors` / `fetchDensity` and from
  the `ViewportQuery` / `ZoneQuery` / `DensityQuery` types in `api.ts`.
- `MapView` data-loading effects: remove the `if (!region) return` guards and the
  `region` dependency keys; loads now fire on viewport + filter changes only.
  Remove the effect that clears layers on `region` change (keep the
  filter-change clear).
- `MobileControlSheet` shows `region` in its header summary today — replace with
  the existing filter summary (`maxLen` / `minExposure`).
- **i18n:** remove the now-unused region key(s) (`region`, and any others found by
  grep) from all three catalogs (`ca`/`es`/`en`) so the parity test stays green.

### Backend `/regions` endpoint

Keep it (cheap, harmless, useful for debugging/tests). The frontend simply stops
calling it. Remove later if desired.

## Edge cases

- **413 "too many in view":** the anchor limit applies to the *merged* total —
  accumulate anchors across all overlapping regions, then compare to
  `MAX_ANCHORS_IN_VIEW` once.
- **Density:** read each overlapping region's `density/z{z}.json` for the
  requested `z` and concatenate; a region without a density pyramid contributes
  nothing.
- **No overlap:** viewport over ocean / between regions → empty FeatureCollection,
  not an error.
- **Cross-border zones (known limitation):** zone clustering (union-find) stays
  per-region, then results are concatenated. A gap straddling two communities'
  precompute bboxes returns two partial zones rather than one stitched zone.
  Acceptable for a "zones to scout" tool where administrative borders don't align
  with cliffs.

## Testing

**Backend**
- A viewport spanning two region fixtures returns merged features from both.
- `region=` still restricts to a single region (back-compat).
- The region index is built once and cached on `app.state`.
- Merged anchor count over `MAX_ANCHORS_IN_VIEW` → 413.
- Viewport with no overlapping region → empty collection.

**Frontend**
- `MapView` loads zones/anchors/density with no `region` param.
- `api.ts` tests: `region` dropped from query strings.
- i18n parity test passes after region key removal.

## Files touched (anticipated)

- `highliner/router/regions.py` — factor out `_bounds_from_grid`.
- `highliner/router/deps.py` (or new small service) — cached region index +
  overlap resolver.
- `highliner/router/zones.py`, `anchors.py`, `density.py` — optional `region`,
  iterate overlapping regions, concatenate.
- `frontend/src/App.tsx`, `components/FilterControls.tsx`,
  `components/MobileControlSheet.tsx`, `components/map/MapView.tsx`,
  `lib/api.ts`, `lib/i18n/strings.ts` — remove region UI/plumbing.
- Corresponding tests.
