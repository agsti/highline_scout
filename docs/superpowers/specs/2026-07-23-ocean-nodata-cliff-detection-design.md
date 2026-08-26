# Ocean-adjacent cliff detection fix

## Problem

`highliner/etls/chunk/terrain.py` — the shared cliff/anchor-extraction algorithm
used by every country — cannot detect cliffs whose exposure faces open ocean.

Confirmed by direct investigation of a known-viable coastal spot in Chile
(`-33.02351, -71.64803`, near Valparaíso): the DTM shows a real cliff (land
rising to ~179 m within 2 km of a sharp coast/ocean boundary), but the nearest
detected anchor is 1.37 km away. Root cause, in `terrain.py`:

1. `compute_slope()` runs `np.gradient` directly over the elevation grid, where
   ocean is `NaN` (nodata). Any land cell within one pixel of the ocean gets an
   **undefined slope**, because the gradient can't be computed across a `NaN`
   neighbor — this erases slope data in a strip right along the coast, exactly
   where a cliff face would be steepest.
2. `extract_anchors()`'s directional exposure sweep does
   `drops = np.where(np.isnan(far), 0.0, base - far)` — if the sweep looks out
   over the ocean (`NaN`), it records **zero drop** instead of the real, often
   large drop to sea level. A cliff whose main exposure faces open water gets
   no credit for that exposure.

This is universal, not Chile-specific: every country's chunk raster collapses
ocean to the same `NaN` sentinel as genuine data-coverage gaps
(`highliner/etls/chunk/dtm_core.py`'s `NODATA`/`SEA_SENTINEL` merge), and
`terrain.py` treats all `NaN` identically regardless of cause.

Out of scope: ALOS PALSAR's 12.5 m resolution also genuinely smooths real
near-vertical cliffs into gentler apparent slopes even away from the ocean
edge. That's a DTM-source-quality problem, not an algorithm bug, and needs a
higher-resolution source (like the LIDAR sourcing done for Italy/France/UK) —
a separate initiative, not addressed here.

## Goal

Make `terrain.py`'s slope/exposure math treat known-ocean cells as an assumed
sea-level elevation (`0.0 m`) instead of `NaN`, while leaving genuine
data-coverage gaps (e.g. Andes SRTM/ALOS voids) untouched as unknown — fixing
them the same way would fabricate false cliffs at data gaps.

## Design

### Mechanism: one universal fix at the raster-loading layer

`terrain.py` itself does not change. Every country's per-chunk raster already
passes through one chokepoint, `raster_from_tiles()` in
`highliner/etls/chunk/dtm_core.py` (`NODATA`/`SEA_SENTINEL` → `NaN`), and then
into `highliner/etls/chunk/shared.py::process_chunk()`, which calls
`raster_from_tiles()` and immediately after has both the resulting raster and
the chunk's `crs` in scope. The fix lands there, as one call right after
`raster_from_tiles()` and before `extract_anchors()` — keeping
`raster_from_tiles()`'s own responsibility narrow (merge tiles only).

That call rasterizes a coastline/ocean reference onto the chunk's exact grid.
For cells that are **both** already `NaN` **and** inside the ocean polygon,
fill with `0.0`. Cells that are `NaN` but not inside the ocean polygon are
left untouched.

This double-gate (must be NaN *and* inside the ocean polygon) means an
imprecise coastline polygon can never overwrite real land elevation, and can
only ever affect cells the DTM itself already reports as nodata — bounding the
blast radius of any polygon inaccuracy to exactly the same cells that are
already blind today.

This single mechanism applies uniformly to all 11 countries, including Spain
and the US, which currently have their own in-source sea sentinel
(`SEA_SENTINEL`, the US's exact-`0.0`-remap) — that in-source signal is
already discarded to plain `NaN` before `terrain.py` sees it today, so those
two countries have the exact same ocean blind spot as Chile. Folding
everything through one coastline-polygon mechanism removes the need to
maintain a second, source-specific path.

### Coastline reference data

Natural Earth's 10 m-scale ocean polygon (public domain, ~few MB, single
download, reused by every country — no per-country sourcing effort).
Precision is coarse (tens of meters), which is fine given the double-gate
above absorbs that imprecision the same way the existing restriction-layer WFS
sources' imprecision is already tolerated elsewhere in this codebase.

Downloaded once to a new non-country-scoped cache location,
`cache/coastline/ne_10m_ocean.*` — the first shared (non-per-country) entry
under `cache/`.

### New module: `highliner/etls/chunk/ocean.py`

- `load_ocean_geometry(crs: str) -> BaseGeometry` — loads the cached Natural
  Earth polygon, clips to a generous bbox, reprojects to `crs`. Cached per CRS
  via `functools.lru_cache` so each worker process reprojects once, not once
  per chunk.
- `fill_ocean_nodata(raster: Raster, ocean_geom: BaseGeometry) -> None` —
  rasterizes `ocean_geom` onto `raster`'s exact grid (`rasterio.features.rasterize`
  with `raster.transform`/`raster.data.shape`) and fills `NaN & ocean` cells
  with `0.0`, in place.

### Wiring

`highliner/etls/chunk/shared.py::process_chunk()` already has `crs` in scope
and already calls `raster_from_tiles()`. Add one call to
`fill_ocean_nodata()` right after, before `extract_anchors()`. This keeps
`raster_from_tiles()`'s responsibility narrow (merge tiles only) and requires
no signature change to it.

### Error handling

- Missing/undownloaded Natural Earth cache file: raise a clear error at
  `load_ocean_geometry()` telling the user how to fetch it (same pattern as
  `chile/restriction/main.py`'s `_load_source` missing-file error).
- An all-ocean chunk (e.g. a pure open-water halo far offshore): `raster_from_tiles`
  still returns a raster (all `NaN`), which `fill_ocean_nodata` turns into flat
  `0.0` — `compute_slope` correctly reports zero slope, so no anchors are
  generated, same practical outcome as today but reached through valid data
  instead of an all-`NaN` raster.

### Testing

- Unit tests in a new `tests/highliner/etls/chunk/test_ocean.py`, following
  the existing `test_dtm_core.py` style: synthetic small raster + synthetic
  polygon, verifying (a) `NaN` cells inside the polygon become `0.0`, (b)
  `NaN` cells outside the polygon are untouched, (c) non-`NaN` (real
  elevation) cells are never overwritten even if they fall inside the polygon.
- No live-network test for the Natural Earth download; tests use a small
  fixture geometry.
- `terrain.py`'s existing tests are unaffected (no code changes there);
  `test_shared.py`'s `process_chunk` tests get one new case exercising a
  synthetic ocean-adjacent chunk end-to-end.

### Rollout (separate step, after code + tests land)

`process_chunk()` already skips any chunk whose pairs parquet exists
(idempotent), so re-running the chunk ETL as-is recomputes nothing. A full
delete-and-rebuild across every chunk in every country would be correct but
wastes hours of compute on chunks nowhere near a coast.

Instead: a small one-off selection script identifies only the chunks whose
halo-bbox intersects the ocean polygon (i.e. genuinely coastal), and deletes
just those chunks' `anchors/`, `pairs/`, and `density/` output files before
rerunning `just etl-chunk <country>` / `just etl-density <country>`.
Landlocked countries (Switzerland, Austria, Czechia) are skipped entirely —
the ocean polygon never intersects them, so the selection script naturally
finds nothing to rebuild there.

This rollout is scoped as follow-up work after the code lands and is
reviewed — not bundled into the same change, given its size and runtime cost.

## Non-goals

- Improving DTM source resolution/quality (separate initiative).
- Per-country custom ocean detection logic (superseded by the single
  coastline-polygon mechanism).
- Any change to `terrain.py`.
