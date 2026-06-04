# Highliner Finder

Find candidate highline spots in Catalonia from ICGC LIDAR terrain.

A highline is a slackline rigged between two cliff anchors and suspended in the
air across a gap. This tool scans terrain elevation data for pairs of steep
points that face each other across a deep gap, at a riggable distance and similar
height — the geometry of a highline.

## How it works

1. **Ingest** — download ICGC bare-earth DTM tiles (2 m, EPSG:25831) for a region.
2. **Analyze** (offline) — compute slope, find cliff-rim **anchor points**, and
   record, per anchor, the **directional sectors** where the ground drops away.
   Stored sparsely as GeoParquet.
3. **Serve** — a FastAPI + Leaflet map pairs anchors live in the current viewport
   (directional gate + exposure check) with adjustable sliders, drawing candidate
   lines.

## Setup

This project uses [`uv`](https://docs.astral.sh/uv/). The geospatial stack
(rasterio, geopandas, pyproj, …) needs a Python with available wheels; a managed
3.12 works well:

    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -e ".[dev]"

(Plain `python -m venv` also works if your interpreter has matching wheels.)

## Use

    # 1. fetch terrain for a bbox (EPSG:25831 meters)
    .venv/bin/highliner ingest --region montserrat \
        --bbox 402000,4606000,406000,4610000
    #    if the fetch returns multiple tiles, build the mosaic:
    #    gdalbuildvrt data/montserrat/mosaic.tif data/montserrat/dtm_*.tif
    #    (single-tile fetches: rename/symlink the tile to mosaic.tif)
    # 2. extract anchors
    .venv/bin/highliner analyze --region montserrat
    # 3. serve the map
    .venv/bin/highliner serve
    # open http://127.0.0.1:8000/

Tune extraction/pairing defaults in `highliner/config.py`.

## Tests

    .venv/bin/python -m pytest

## Caveat

Results are **candidates to scout**, not confirmed-riggable lines. Terrain data
cannot reveal bolts, trees, loose rock, access, or permissions. Scout responsibly.
