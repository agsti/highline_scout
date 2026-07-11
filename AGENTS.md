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

The frontend is a Vite + React + TypeScript app under `frontend/` (Node ≥ 20):

    just install-web               # npm ci (once, and after dependency changes)
    just dev-web                   # Vite hot-reload UI on :5173, proxies API to :8000
    just build-web                 # production build -> frontend/dist/ (served by FastAPI)
    just test-web                  # frontend test suite (vitest)

Local dev and production serve the frontend differently:

- **Local** — run `just dev` (API on :8000) and `just dev-web` (Vite on :5173)
  together, and open **:5173**. Vite serves the UI and proxies/rewrites the API
  routes (`/regions`, `/zones`, `/density`, `/anchors`, `/restrictions`) to
  :8000, so the backend never serves frontend assets. No `build-web` needed.
- **Production** — the Docker build runs `build-web` and FastAPI mounts the
  resulting `frontend/dist/` at `/` (`app.py`, guarded by the dir existing).
  Keep the Vite `server.proxy` list in `vite.config.ts` in sync with the API
  route prefixes.

CLI (`highliner` entry point, `highliner/cli.py`):

    .venv/bin/highliner precompute --region NAME --bbox minx,miny,maxx,maxy [--chunk-km N]
    .venv/bin/highliner precompute-density --region NAME
    .venv/bin/highliner serve

## Telemetry

Analytics and error reporting are **off unless configured**, so local dev sends
nothing and needs no setup.

- **Frontend** (`frontend/src/lib/analytics.ts`) — PostHog, initialized only in a
  production build on a non-local hostname. Autocapture plus four events bound to
  committed actions: `filter_changed`, `zone_opened`, `restriction_layer_toggled`,
  and a debounced `map_settled`. Never bind analytics to a slider's
  `onValueChange` or to a raw `moveend` — those fire per drag frame, and one
  gesture would be recorded dozens of times.
- **Analytics is deliberately cookieless, and must stay that way.**
  `persistence: "memory"` writes nothing to the visitor's device and
  `person_profiles: "identified_only"` keeps events anonymous, which is why the
  app needs no cookie consent banner. `cookieless_mode: "always"` recovers
  *same-day* unique-visitor counts on top of that: PostHog hashes IP +
  User-Agent + a salt that rotates daily into a visitor ID server-side, so
  same-day counts are meaningful again — with **zero** additional device
  storage. What is still lost is cross-*day* identity: a visitor's hashed ID
  changes every day, so **retention and cohort analysis spanning days remain
  meaningless**. The tempting fix is to switch `persistence` back to
  `localStorage+cookie`: that is exactly what reintroduces the cookie, and with
  it the consent obligation. Don't. (Nor `person_profiles: "always"` — it would
  not fix that anyway, it would just create a person profile per pageview.)
- **Backend** (`highliner/core/telemetry.py`) — deliberately thin. The server
  only sees viewport reads, so it emits **no per-request events**: just a
  `slow_request` when a handler exceeds `HIGHLINER_SLOW_REQUEST_MS` (default
  1000). Errors go to GlitchTip via `sentry_sdk`, never to PostHog, so nothing is
  double-counted.
- **Config** — `HIGHLINER_POSTHOG_KEY`, `HIGHLINER_SENTRY_DSN`,
  `HIGHLINER_ENVIRONMENT`, `HIGHLINER_SLOW_REQUEST_MS`. In production these come
  from sops-encrypted secrets in the separate `vps` repo
  (`highliner/secrets.enc.env`).

## Package layout

The package is organized into layers (MVC-ish). Each module is one domain's
slice of that layer:

    highliner/
      app.py                 FastAPI factory: wires routers, CORS, and the
                             frontend/dist/ static mount
      cli.py                 `highliner` entry point (precompute/precompute-density/serve/fetch-restrictions)
      core/                  cross-cutting: config.py, geo.py (coord transforms)
      models/                pure domain dataclasses: anchor, candidate, zone, raster
      repositories/          persistence & external IO: anchors (parquet), dtm
                             (ICGC WCS), restrictions (national MITECO files)
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

2. **Serve** (`app.py` + `router/`) — FastAPI + a Vite/React frontend in
   `frontend/` (Leaflet map), served in production from its `frontend/dist/` build.
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
reporting the min/max exposure across its pairs as a height range. When a
viewport straddles multiple precomputed regions, `/zones` reprojects all
in-view candidates into the westernmost region's CRS, dedups near-duplicate
seam pairs, and runs a single union-find so border-straddling zones aren't
fragmented; single-region requests are unchanged.

**Coordinate convention**: everything internal is UTM EPSG:25831 (meters) — ICGC
native, needed for distance/slope math. Conversion to/from WGS84 lon/lat happens
only at the web boundary, in `core/geo.py` (and the GeoJSON serializers in
`router/serializers.py`). API bbox params accept either `bbox` (UTM) or
`bbox_lonlat`.

**Restrictions** (`repositories/restrictions.py` for download/storage +
`services/restrictions.py` for serving): informational protected-area overlays
covering all of Spain, built from MITECO's (national) Banco de Datos de la
Naturaleza files — Red Natura 2000 GML (INSPIRE ProtectedSites) and Espacios
Naturales Protegidos GeoJSON, each shipped as a peninsula+Baleares file and a
Canarias file in different CRSes. `just fetch-restrictions` downloads the raw
files into `data/restrictions/raw/` and runs `highliner fetch-restrictions`
to derive three layers — `zepa` (Special Protection Area for Birds) and `zec`
(Site/Area of Community Importance), both filtered from the RN2000 GML by
designation code (parsed from the raw XML, since GDAL doesn't expose it as an
attribute), plus `enp` (Protected Natural Areas) from the ENP GeoJSON —
written to `data/restrictions/<id>.parquet` and clipped to the viewport on
`GET /restrictions`. Tooltips are in English (the base/source-of-truth
language for restrictions text; see i18n below).

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
English (`en`)**. It lives under `frontend/src/lib/i18n/`, exposed as a React
context: `I18nProvider` wraps the app and `useI18n()` hands components
`{ lang, setLang, t }`.

### Where strings live

- **`frontend/src/lib/i18n/strings.ts` → `STRINGS[lang]`** — every UI string,
  one flat object per language. Catalan (`ca`) is the base/source-of-truth key
  set, and `StringKey` is derived from it (`keyof typeof STRINGS.ca`), so `t()`
  calls type-check against the `ca` keys.
- **`frontend/src/lib/i18n/restrictionStrings.ts` → `RESTRICTION_STRINGS[lang]`**
  — per-layer protected-area text (`label` / `tooltip` / `highlight`), keyed by
  layer id (`zepa`, `zec`, `enp`). **English is intentionally absent here**
  — it comes from the backend (see below) and must not be duplicated.
- **`highliner/repositories/restrictions.py`** — the **English** restriction
  `label` / `tooltip` / `highlight`, served via `/restrictions`. This is the
  `en` source and the fallback for any layer without a translation.

### How `t()` and rendering work

- `t(key, params)` (from `useI18n()`) looks up `STRINGS[lang][key]` and
  interpolates `{name}` placeholders from `params`. A missing key returns the
  key itself, so gaps show on screen instead of going blank.
- Some strings are **HTML** (they feed Leaflet popups/tooltips): `zonePopup`,
  `densityTooltip`, `anchorPopup`, etc. Keep them valid HTML.
- `restrictionText(id, lang, fallback)` resolves a layer's text for the active
  language, falling back to the server-provided English `{label,tooltip,highlight}`.
- `RestrictionLayerControls` shows a `restrictionCredit` line ("Protected-area
  data © MITECO", translated) crediting the national data source.
- `LanguageSwitcher` calls `setLang()`; because the whole tree consumes the i18n
  context, switching re-renders every component (labels, legend, popups) and
  `I18nProvider` persists the choice to `localStorage` and sets
  `document.documentElement.lang`.

### Adding or changing a UI string

1. Add the key to **all three** `STRINGS` catalogs (`ca`, `es`, `en`). The
   catalog-parity test in `frontend/src/lib/i18n/i18n.test.tsx` fails if any
   catalog's key set differs from `ca`, and TypeScript flags stray/missing keys
   at `t()` call sites.
2. Use it via `const { t } = useI18n()` then `t("key")`.
3. For placeholders, use `{name}` and pass `t("key", { name: value })`.

### Adding a restriction-layer translation

Add the layer id under `RESTRICTION_STRINGS[es]` and `[ca]` with `label`,
`tooltip`, `highlight`. **Invariant:** per language, `highlight` MUST be a
verbatim substring of `tooltip` — the panel marks it via `indexOf()`. Do not add
an `en` entry; the English text lives in the backend repository.

### Adding a new language

1. Add the code to `LANGS` in `strings.ts` and a full `STRINGS` object with the
   **same key set as `ca`**.
2. Add the language's `RESTRICTION_STRINGS` entry (optional — falls back to
   Catalan otherwise).
3. `pickInitialLang()` (in `I18nProvider.tsx`) auto-detects it from the browser
   (2-letter prefix) and remembers the choice in `localStorage`;
   `LanguageSwitcher` picks up the new `LANGS` entry automatically.
