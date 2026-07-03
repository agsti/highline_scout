# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Finds potential highline zones in Catalonia from ICGC LIDAR terrain. A highline is
a slackline rigged between two cliff anchors across a deep gap. The tool scans
bare-earth elevation rasters for cliff-rim anchor points, pairs anchors that face
each other across a riggable gap, and clusters the pairs into **zones** rendered
on a web map. Results are *zones to scout*, never confirmed-riggable lines.

## Setup & commands

Uses [`uv`](https://docs.astral.sh/uv/). The geospatial stack (rasterio,
geopandas, pyproj) needs Python with available wheels — use a managed 3.12; the
system interpreter's plain `venv` is known-broken here.

    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -e ".[dev]"

    just test                      # full suite (uv run pytest)
    uv run pytest tests/test_pairing.py::test_name   # single test
    just dev                       # FastAPI dev server, auto-reload, :8000
    just fetch-restrictions        # download protected-area layers -> data/restrictions/

CLI (`highliner` entry point, `highliner/cli.py`):

    .venv/bin/highliner ingest --region NAME --bbox minx,miny,maxx,maxy   # EPSG:25831
    .venv/bin/highliner analyze --region NAME
    .venv/bin/highliner serve

## Package layout

The package is organized into layers (MVC-ish). Each module is one domain's
slice of that layer:

    highliner/
      app.py                 FastAPI factory: wires routers, CORS, and the
                             web/ static mount
      cli.py                 `highliner` entry point (ingest/analyze/serve/fetch-restrictions)
      core/                  cross-cutting: config.py, geo.py (coord transforms)
      models/                pure domain dataclasses: anchor, candidate, zone, raster
      repositories/          persistence & external IO: anchors (parquet), dtm
                             (ICGC WCS), restrictions (Generalitat WFS)
      services/              domain logic: terrain, pairing, zones,
                             restrictions (serving helpers)
      router/                HTTP layer: one APIRouter per resource (regions,
                             zones, anchors, density, restrictions) plus
                             deps.py (bbox parsing, region cache, app.state access)
                             and serializers.py (domain → GeoJSON)

Dependencies flow router → services/tasks → repositories → models/core.

## Architecture

Three stages. The expensive geospatial work (1, 2) is done offline and cached;
the server (3) only does cheap in-viewport pairing on every request.

1. **Ingest** (`repositories/dtm.py`) — downloads ICGC bare-earth DTM (5 m,
   EPSG:25831) over a WCS endpoint. Each request is capped at ~140 KB, so a bbox
   is fetched as a grid of small ArcGrid tiles and merged into one `mosaic.tif`.
   Tiles and the mosaic are cached on disk; an existing `mosaic.tif` is returned
   untouched.

2. **Analyze** (`services/pipeline.py` → `services/terrain.py`) — `extract_anchors`
   computes slope, takes steep cells as candidate cliff cells, and for each sweeps
   azimuths (`drop_sectors`) to record the **directional sectors** where ground
   drops away. Greedy non-max suppression (`_thin`) spaces anchors out. The
   `Anchor` model (`models/anchor.py`) is stored sparsely as GeoParquet
   (`repositories/anchors.py`): each anchor keeps its `(start, end, max_drop)`
   sectors so pairing can later test bearings without re-reading the raster.

3. **Serve** (`app.py` + `router/`) — FastAPI + a Leaflet frontend in `web/`. On
   each `GET /zones` (`router/zones.py`) it filters anchors to the viewport bbox,
   runs `find_candidates` (`services/pairing.py`), and builds zones
   (`services/zones.py`). Pairing defaults are exposed as live sliders.

**Pairing** (`services/pairing.py`): for anchor pairs within `max_len`, gates on
length, height difference, a **directional check** (each anchor's bearing to the
other must fall within one of its drop sectors, ± `SECTOR_TOL_DEG`), and
**exposure** (lower anchor's elevation minus the lowest terrain point strictly
between them, sampled along the line). Exposure is the highline's height.

**Zones** (`services/zones.py`): clusters paired anchors via union-find — pair
endpoints always merge (joining both rims of a gap), plus any paired anchors
within `cluster_dist`. Each zone is the convex hull (buffered) of its anchors,
reporting the min/max exposure across its pairs as a height range.

**Coordinate convention**: everything internal is UTM EPSG:25831 (meters) — ICGC
native, needed for distance/slope math. Conversion to/from WGS84 lon/lat happens
only at the web boundary, in `core/geo.py` (and the GeoJSON serializers in
`router/serializers.py`). API bbox params accept either `bbox` (UTM) or
`bbox_lonlat`.

**Restrictions** (`repositories/restrictions.py` for download/storage +
`services/restrictions.py` for serving): informational protected-area overlays
(PEIN, Parcs Naturals, Reserves de Fauna) downloaded once from the Generalitat
WFS into `data/restrictions/<id>.parquet`, clipped to the viewport on
`GET /restrictions`. Tooltips are in Catalan. The WFS rejects the default
requests User-Agent with 403 — a custom UA header is required.

## Data layout (gitignored)

    data/<region>/mosaic.tif        merged DTM raster
    data/<region>/anchors.parquet   extracted anchors + sectors
    data/<region>/tiles/            cached ArcGrid download tiles
    data/restrictions/<id>.parquet  protected-area overlays

## Tuning

`highliner/core/config.py` is the single source of extraction, pairing, and
clustering parameters. Note the shipped pairing defaults (`MIN_EXPOSURE_M=30`,
`MAX_DH_M=10`) are strict enough to hide some real known highlines — loosen them
when validating against known lines.
