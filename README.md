# Highliner Finder

Find potential highline zones in Catalonia from ICGC LIDAR terrain.

A highline is a slackline rigged between two cliff anchors and suspended in the
air across a gap. This tool scans terrain elevation data for **zones** —
clusters of nearby cliff-rim points where at least two anchors face each other
across a deep gap at a riggable distance. Each zone reports its highline
height range: per pair, the lower anchor's elevation minus the lowest terrain
point between the anchors.

## How it works

1. **Precompute** (offline) — tile a region's bbox into chunks; for each chunk,
   download ICGC bare-earth DTM (5 m, EPSG:25831), compute slope, find cliff-rim
   **anchor points** with their **directional sectors** (where the ground drops
   away), and pair facing anchors across a gap (directional gate + exposure
   check) at a loose envelope. Anchors and candidate pairs are stored sparsely
   as GeoParquet partitions; the raw DTM is discarded once a chunk is processed
   — nothing raster-shaped persists on disk.
2. **Serve** — a FastAPI + Leaflet map reads the precomputed pairs in the
   current viewport, narrows them with adjustable sliders (length, height
   difference, exposure), clusters the survivors, and draws potential **zones**
   colored by highline height.

## Setup

This project uses [`uv`](https://docs.astral.sh/uv/). The geospatial stack
(rasterio, geopandas, pyproj, …) needs a Python with available wheels; a managed
3.12 works well:

    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -e ".[dev]"

(Plain `python -m venv` also works if your interpreter has matching wheels.)

## Use

    # 1. precompute anchors + candidate pairs for Spain (8 workers)
    just etl-chunk spain 8
    # 2. serve the map
    .venv/bin/highliner-server
    # open http://127.0.0.1:8000/

Tune extraction/pairing defaults in `highliner/core/config.py`.

## Protected-area overlays

The map can overlay Catalan protected-area boundaries (Natura 2000 ZEC/ZEPA,
PEIN, Parcs Naturals, Reserves de Fauna) so you can see whether a potential
zone falls in a restricted area. Download them once from the Generalitat WFS:

    just etl-restriction spain   # -> data/spain/restrictions/<layer>.parquet

Then toggle the layers from the **Restrictions** panel on the map. They are
informational only — being outside a drawn area does not imply rigging is
allowed. Always confirm access and permissions on the ground.

## Tests

    .venv/bin/python -m pytest

## Caveat

Results are **zones to scout**, not confirmed-riggable lines. Terrain data
cannot reveal bolts, trees, loose rock, access, or permissions. Scout responsibly.
