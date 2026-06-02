# Highliner Finder — Design

**Date:** 2026-06-02
**Status:** Approved (brainstorming)

## Purpose

A personal tool to discover candidate **highline** spots in Catalonia from ICGC
LIDAR terrain data. A highline is a slackline rigged between two cliff anchors
and suspended in the air across a gap.

A valid candidate is a pair of points **A** and **B** where:

1. Both sit on **steep terrain** (cliff edge) — solid anchors.
2. **Distance(A, B) ≤ the rigging line length** (with a small minimum too).
3. **A and B are at similar elevation** — the line is roughly level.
4. The **ground between them drops away** far below the anchors — the air/exposure
   that makes it a highline rather than a groundline.

**Honesty caveat (surfaced in the UI):** results are *candidates to scout*, not
confirmed-riggable lines. From terrain data alone we cannot see bolts, trees,
loose rock, access, or legal/permission constraints.

## Scope decisions (from brainstorming)

- **Form factor:** interactive map app.
- **Data source:** ICGC Catalonia DTM (bare-earth, ~1–2 m, EPSG:25831 / UTM 31N).
  The tool fetches tiles for a region.
- **Scale:** large region **precomputed offline**; map browses/queries results.
- **Stack:** Python backend + JavaScript map frontend.
- **Reconciling precompute with live sliders (Approach A):** precompute sparse
  **anchor points** offline; **pair them on-the-fly** in the current viewport with
  live slider filtering. Live sliders, tiny storage, cheap per-view compute.

### User-adjustable controls (sliders)

- **Max line length** (e.g. 50–300 m) — rejects pairs farther apart.
- **Min exposure / height** — how far the ground must drop below the anchors.
- **Anchor height tolerance** — max elevation difference between the two anchors.

## Architecture

Three parts with clean boundaries:

### 1. Ingest (offline CLI)

Given a region bounding box, download ICGC DTM tiles, cache them locally, and
build a mosaic/VRT. Idempotent and cached so re-runs are cheap. Skips tiles with
no coverage (warn), retries on transient network errors.

**Interface:** `highliner ingest --bbox <minx,miny,maxx,maxy> --region <name>`
**Depends on:** ICGC tile endpoint, local `data/` cache.

### 2. Analyze (offline CLI)

From the cached DTM mosaic for a region:

1. Compute **slope** (degrees) from the elevation gradient.
2. For each candidate cell, compute **local elevation drop** within a short
   radius `R` — how far the ground falls nearby. High drop = cliff rim.
3. **Directional drop sectors:** sample the drop across a full azimuth sweep
   (every ~10–15°) within radius `R`. The azimuths where the ground drops
   meaningfully form **one or more angular sectors** (a knife-edge point can drop
   on two+ sides). Keep a cell as an anchor only if it has ≥1 qualifying sector.
4. **Thin** anchors (non-max suppression / grid-snap) to sparse representative
   points.

**Anchor record:** `position (UTM x,y)`, `elevation`, `sectors: [(start°, end°, max_drop)]`.

Written to a per-region anchor store (**GeoParquet**).

**Interface:** `highliner analyze --region <name>`
**Depends on:** cached DTM mosaic (from ingest).

### 3. Serve (API + web)

FastAPI loads a region's anchors into memory and builds a KDTree. Frontend is a
Leaflet map (ICGC orthophoto + hillshade basemap) with the three sliders. On
pan/zoom or slider change it calls the candidates endpoint; backend pairs anchors
live and returns GeoJSON lines.

**API:**
- `GET /regions` — list precomputed regions.
- `GET /candidates?bbox=&max_len=&min_exposure=&max_dh=` — GeoJSON candidate lines
  in the viewport, filtered live.

**Depends on:** anchor store (from analyze), cached DTM (for exposure sampling).

## Core algorithm — online pairing (the heart)

For anchors within the current viewport:

1. **Neighbor query:** KDTree → anchor pairs within **max line length** (and ≥ a
   small minimum length).
2. **Height tolerance:** reject pairs with elevation difference > **max_dh**.
3. **Directional gate:** require `bearing(A→B)` inside one of **A**'s drop sectors
   **and** `bearing(B→A)` inside one of **B**'s sectors (with angular tolerance).
   Guarantees the gap lies *between* the anchors — both cliffs face the void.
4. **Exposure check:** sample DTM elevations along the straight segment at DTM
   resolution; require
   `min(elev A, elev B) − lowest ground along span ≥ min_exposure`, and that the
   low point is **interior** (a real gap, not just a downhill slope).
5. **Dedup** (A,B)≡(B,A), **score** (exposure + steepness + levelness), return
   **top N** as GeoJSON LineStrings with properties: `length`, `exposure`,
   `height_diff`, `score`.

## Key technical decisions

- **DTM (bare earth)** for gap geometry. DSM/vegetation clearance is a noted
  future enhancement.
- All raster math in **UTM meters** — distances are real meters; convert to
  lon/lat only for the map/GeoJSON.
- Anchors held **in memory** per region (sparse → tens of thousands fine).
  SpatiaLite/R-tree is the documented scale-up path if a region gets too big.

## Stack

- **Python:** `fastapi`, `uvicorn`, `rasterio`, `numpy`, `scipy` (KDTree +
  gradients), `pyproj`, `shapely`, `geopandas`/`pyarrow` (GeoParquet),
  `requests`.
- **Frontend:** Leaflet + vanilla JS (no build step).
- **Data:** cached under `data/` (gitignored).

## Error handling

- **ICGC fetch:** retry on transient failures; skip no-coverage tiles with a
  warning; cache everything.
- **No anchors in region:** clear message.
- **Viewport too large / too many anchors:** return a "zoom in" hint rather than
  hang.
- **CRS correctness:** explicit, tested transforms between EPSG:25831 and
  EPSG:4326/3857.

## Testing

- Synthetic numpy DTMs with a **hand-built canyon** of known geometry → assert
  anchor extraction, directional sectors, segment sampling, exposure, length, and
  each pairing filter independently.
- CRS-transform tests on known points.
- API tests against a tiny fixture region.

## Project layout

```
highliner/
  __init__.py
  config.py
  ingest.py     # ICGC tile fetch + mosaic
  terrain.py    # slope, drop, directional sectors, anchor extraction
  anchors.py    # anchor store read/write (GeoParquet)
  geo.py        # CRS transforms, segment sampling, bearings
  pairing.py    # KDTree pairing + directional gate + exposure + filters
  scoring.py    # candidate quality score
  api.py        # FastAPI
  cli.py        # ingest / analyze / serve commands
web/
  index.html
  app.js
  style.css
tests/
data/           # cached tiles + anchor stores (gitignored)
docs/superpowers/specs/
```

## Future enhancements (out of scope for v1)

- DSM-based vegetation/structure clearance check along the span.
- Reject candidates blocked by a mid-span pinnacle (full whole-span clearance vs.
  current min-ground check).
- Multi-region / nationwide (PNOA) coverage.
- Access/approach routing and difficulty.
- Persisted candidate store (SpatiaLite) for very large regions.
