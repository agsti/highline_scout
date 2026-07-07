# AGENTS.md

This file provides guidance to coding agents (Claude Code, etc.) when working
with code in this repository.

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

    .venv/bin/highliner precompute --region NAME --bbox minx,miny,maxx,maxy [--chunk-km N]
    .venv/bin/highliner precompute-density --region NAME
    .venv/bin/highliner serve

## Package layout

The package is organized into layers (MVC-ish). Each module is one domain's
slice of that layer:

    highliner/
      app.py                 FastAPI factory: wires routers, CORS, and the
                             web/ static mount
      cli.py                 `highliner` entry point (precompute/precompute-density/serve/fetch-restrictions)
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

Two stages. All geospatial work is done offline by `precompute` and cached as
parquet partitions; the server only does cheap in-viewport reads and filtering
on every request — no DTM raster is ever touched at serve time.

1. **Precompute** (`highliner precompute`, `services/precompute.py`) — tiles
   the region's bbox into `chunk_m`-sized squares (`chunk_grid`). For each chunk
   (`process_chunk`): downloads ICGC bare-earth DTM tiles (5 m, EPSG:25831) over
   a WCS endpoint for the chunk's core plus a halo (`repositories/dtm.py`; each
   WCS request is capped at ~140 KB, so tiles are downloaded individually and
   merged in memory), runs `extract_anchors` (`services/terrain.py` — slope
   threshold, directional drop-sector sweep, greedy non-max-suppression spacing)
   to get anchors, then `find_candidates` (`services/pairing.py`) to get
   candidate pairs (length / height-diff / directional / exposure gated,
   exposure computed by sampling the raster between each pair) at a loose
   envelope. Anchors owned by the chunk's core and pairs whose canonical endpoint
   falls in the core are written as `anchors/p_{cx}_{cy}.parquet` /
   `pairs/q_{cx}_{cy}.parquet` (`repositories/anchors.py`,
   `repositories/candidates.py`); the raw DTM tiles are deleted afterward —
   nothing raster-shaped persists.

2. **Serve** (`app.py` + `router/`) — FastAPI + a Leaflet frontend in `web/`.
   On each `GET /zones` (`router/zones.py`) it reads the precomputed pair
   partitions overlapping the viewport (`repositories/chunked_store.py`),
   narrows them with the live `min_len`/`max_len`/`min_exposure`/`max_dh`
   sliders (`services/pairing.filter_candidates`), and clusters them into zones
   (`services/zones.py`). `GET /anchors` reads the overlapping anchor partitions
   the same way.

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

    data/<region>/grid.json                       {bbox, chunk_m}
    data/<region>/anchors/p_{cx}_{cy}.parquet     anchors per chunk
    data/<region>/pairs/q_{cx}_{cy}.parquet       candidate pairs per chunk (exposure baked in)
    data/<region>/tiles/                          transient DTM tile cache, deleted once a chunk finishes
    data/<region>/density/z{z}.json               zoomed-out density pyramid (optional, `precompute-density`)
    data/restrictions/<id>.parquet                protected-area overlays

## Tuning

`highliner/core/config.py` is the single source of extraction, pairing, and
clustering parameters. Note the shipped pairing defaults (`MIN_EXPOSURE_M=30`,
`MAX_DH_M=10`) are strict enough to hide some real known highlines — loosen them
when validating against known lines.

## Localization (i18n)

The frontend is trilingual: **Catalan (`ca`, default) / Spanish (`es`) /
English (`en`)**. There is no build step — `web/i18n.js` is a plain `<script>`
loaded before `web/app.js`, exposing `STRINGS`, `LANG`, `t()`, `setLang()`,
`applyStaticI18n()` and `restrictionText()` as globals.

### Where strings live

- **`web/i18n.js` → `STRINGS[lang]`** — every UI string, one flat object per
  language. Catalan (`ca`) is the base/source-of-truth key set.
- **`web/i18n.js` → `RESTRICTION_STRINGS[lang]`** — per-layer protected-area
  text (`label` / `tooltip` / `highlight`), keyed by layer id (`pein`, `parcs`,
  `fauna`). **Catalan is intentionally absent here** — it comes from the backend
  (see below) and must not be duplicated.
- **`highliner/repositories/restrictions.py`** — the **Catalan** restriction
  `label` / `tooltip` / `highlight`, served via `/restrictions`. This is the
  `ca` source and the fallback for any layer without a translation.

### How `t()` and rendering work

- `t(key, params)` looks up `STRINGS[LANG][key]` and interpolates `{name}`
  placeholders from `params`. A missing key returns the key itself, so gaps show
  on screen instead of going blank.
- Some strings are **HTML** (they feed Leaflet popups/tooltips): `zonePopup`,
  `densityTooltip`, `anchorPopup`, etc. Keep them valid HTML.
- Static markup uses `data-i18n="key"` attributes (`web/index.html`);
  `applyStaticI18n()` fills them on load and after each switch.
- `restrictionText(id, fallback)` resolves a layer's text for the active
  language, falling back to the server-provided Catalan `{label,tooltip,highlight}`.
- The language switcher (`#lang` select in `web/index.html`, wired at the bottom
  of `web/app.js`) calls `setLang()` then re-renders **everything**:
  `applyStaticI18n()`, drops the density legend so `refresh()` rebuilds it, and
  re-runs `refresh()` / `refreshAnchors()` / `refreshRestrictions()`.

### Adding or changing a UI string

1. Add the key to **all three** `STRINGS` catalogs (`ca`, `es`, `en`) — the
   dev-only `assertCatalogParity()` check warns in the console if any catalog's
   key set differs from `ca`.
2. Use it via `t("key")` in JS, or `data-i18n="key"` for static markup (with an
   English fallback in the element's text so it's readable pre-JS).
3. For placeholders, use `{name}` and pass `t("key", { name: value })`.

### Adding a restriction-layer translation

Add the layer id under `RESTRICTION_STRINGS[es]` and `[en]` with `label`,
`tooltip`, `highlight`. **Invariant:** per language, `highlight` MUST be a
verbatim substring of `tooltip` — the panel marks it via `indexOf()`. Do not add
a `ca` entry; the Catalan text lives in the backend repository.

### Adding a new language

1. Add a full object under `STRINGS` with the **same key set as `ca`**.
2. Add the language's `RESTRICTION_STRINGS` entry (optional — falls back to
   Catalan otherwise).
3. Add an `<option>` to the `#lang` select in `web/index.html`.
4. `pickInitialLang()` auto-detects it from the browser (2-letter prefix) and
   remembers the choice in `localStorage`; no other wiring needed.
