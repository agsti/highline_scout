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

For an isolated git worktree, create a separate `.venv` and run the same dev
install there. Do not symlink a worktree's `.venv` to another checkout: virtual
environment paths are checkout-specific. `uv` shares its download/build cache
automatically, so separate environments remain quick and isolated.

    just test                      # full suite (uv run pytest)
    uv run pytest tests/test_pairing.py::test_name   # single test
    just check                     # lint (ruff) + types (strict mypy) + dead code
    just lint --fix                # ruff, applying safe autofixes
    just deadcode                  # vulture, on its own
    just dev                       # FastAPI dev server, auto-reload, :8000
    just etl-chunk-8               # precompute configured countries (8 workers)
    just etl-density-8             # build country density layers (8 workers)
    just etl-restriction           # build protected-area layers by country

CI runs `ruff check`, the file-length cap, `mypy`, `vulture` and `pytest`;
`pre-commit install` runs everything but the tests on commit. Ruff is lint-only
(rules `E,F,I,UP,B,C90,PLR09xx` at 88 columns) — there is no autoformatter, so
match the surrounding style by hand.

Vulture (`[tool.vulture]`) reports definitions nothing references. It scans
`highliner/` and `scripts/` but **not** `tests/`, so a function only its own
test calls is reported as dead — that's deliberate, since a green test over an
uncalled function proves nothing about the product. When it fires, delete the
code and the test together, or re-point the test at whatever superseded it.
Names a framework reaches by convention (pydantic's `model_config`, Starlette's
`dispatch`, `@router.*` handlers) are excused in `ignore_names` /
`ignore_decorators`; extend that list rather than working around it in source.

Complexity is capped: cyclomatic complexity 10 per function, 12 branches, 50
statements, 5 arguments, and 500 lines per file (the last has no ruff rule, so
`scripts/check_file_length.py` enforces it). Twelve pre-existing signatures
carry `# noqa: PLR0913` — FastAPI query params and geospatial tuning knobs that
legitimately exceed 5 arguments. Prefer splitting the function over adding a
new `noqa`.

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
  resulting `frontend/dist/` at `/` (`server/app.py`, guarded by the dir existing).
  Keep the Vite `server.proxy` list in `vite.config.ts` in sync with the API
  route prefixes.

CLI entry points:

    uv run python -m highliner.etls.chunk.spain [--workers N]
    uv run python -m highliner.etls.density.spain [--data-dir PATH] [--workers N]
    .venv/bin/highliner-server
    uv run python -m highliner.etls.restriction.spain

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
- **Cookieless mode must be enabled in the PostHog project settings, or every
  event is silently discarded at ingestion.** This is a hard dependency on
  dashboard state that nothing in this repo can enforce and no test can catch —
  the suite is green either way, and the only symptom is that production
  analytics reads zero. If cookieless mode is ever turned off in the project
  settings, or the project is recreated, `cookieless_mode: "always"` in
  `analytics.ts` must go too. The safe order when changing either: enable the
  project setting **first**, deploy the code **second**.
- The four `disable_*` flags in `analytics.ts` (session recording, surveys,
  product tours, conversations) are pinned off because each is independently
  toggleable from the PostHog dashboard and each would otherwise write to the
  device — with no code change and no failing test. Enabling any of them from
  the dashboard would silently falsify the privacy disclosure users are shown.
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

The package is split top-level by the two stages — `etls/` (offline precompute)
and `server/` (serving) — over a shared `core/` + `models/` foundation. Each
stage keeps the same layered structure (repositories / services, plus router on
the server). Command entry points live beside the stage they drive:

    highliner/
      core/                  shared cross-cutting: config, geo (coord transforms),
                             regions, tiles, telemetry, restrictions (the LAYERS
                             overlay registry both stages consume)
      models/                shared pure domain dataclasses: anchor, candidate, zone, raster
      etls/                  country adapters plus offline precompute pipeline
        chunk/               country-neutral chunk precompute utilities plus adapters,
                             DTM download, terrain extraction, pairing, and parquet writers
          spain.py           Spain chunk-precompute command
          shared.py          chunk-grid orchestration
          dtm.py             ICGC/IGN WCS terrain download
          terrain.py         anchor extraction
          pairing.py         candidate pairing
          anchors.py         anchor parquet writer
          candidates.py      candidate parquet writer
        density/             country density adapters and aggregation
        restriction/         country protected-area adapters
      server/                serving
        main.py              server command
        app.py               FastAPI factory: wires routers, CORS, and the
                             frontend/dist/ static mount
        repositories/        chunked_store (viewport reads), partition_cache
                             (process-wide columnar LRU + vectorized viewport/
                             slider masks), candidates (parquet read side),
                             restrictions (load stored layers)
        services/            zones, restrictions (serving helpers)
        router/              HTTP layer: one APIRouter per resource (regions,
                             zones, anchors, density, restrictions) plus
                             deps.py (bbox parsing, region cache, app.state access)
                             and serializers.py (domain → GeoJSON)
      restrictions/main.py   protected-area build command

Dependencies flow router → services → repositories → models/core, and both
stages depend only on the shared `core/` + `models/`. The one exception is the
offline `etls/density/`, which aggregates the already-precomputed
store and so reads back through the server-side read layer
(`server/repositories/chunked_store` + `candidates`); that dependency only ever
points etls → server, never the reverse.

## Architecture

Two stages. All geospatial work is done offline by `precompute` and cached as
parquet partitions; the server only does cheap in-viewport reads and filtering
on every request — no DTM raster is ever touched at serve time.

1. **Precompute** (`highliner.etls.chunk.<country>`, `etls/chunk/shared.py`) — tiles
   the region's bbox into `chunk_m`-sized squares (`chunk_grid`). For each chunk
   (`process_chunk`): downloads ICGC bare-earth DTM tiles (5 m, EPSG:25831) over
   a WCS endpoint for the chunk's core plus a halo (`etls/chunk/dtm.py`; each
   WCS request is capped at ~140 KB, so tiles are downloaded individually and
   merged in memory), runs `extract_anchors` (`etls/chunk/terrain.py` — slope
   threshold, directional drop-sector sweep, greedy non-max-suppression spacing)
   to get anchors, then `find_candidates` (`etls/chunk/pairing.py`) to get
   candidate pairs (length / height-diff / directional / exposure gated,
   exposure computed by sampling the raster between each pair) at a loose
   envelope. Anchors owned by the chunk's core and pairs whose canonical endpoint
   falls in the core are written as `anchors/p_{cx}_{cy}.parquet` /
   `pairs/q_{cx}_{cy}.parquet` (`etls/chunk/anchors.py`,
   `etls/chunk/candidates.py`); the raw DTM tiles are deleted afterward —
   nothing raster-shaped persists.

2. **Serve** (`server/app.py` + `server/router/`) — FastAPI + a Vite/React frontend in
   `frontend/` (Leaflet map), served in production from its `frontend/dist/` build.
   On each `GET /zones` (`server/router/zones.py`) it reads the precomputed pair
   partitions overlapping the viewport (`server/repositories/chunked_store.py`),
   narrowing them by both the viewport window and the live
   `min_len`/`max_len`/`min_exposure`/`max_dh` sliders — passed down as a
   `PairFilter` and applied as vectorized masks over the cached partition
   columns, so only surviving pairs become `Candidate` objects — then clusters
   them into zones (`server/services/zones.py`). `GET /anchors` reads the
   overlapping anchor partitions the same way, clipped to the viewport at read
   time. Partitions are parsed once into NumPy columns and cached process-wide
   (`server/repositories/partition_cache.py`), so panning re-hits warm
   partitions without re-reading or re-parsing.

**Pairing** (`etls/chunk/pairing.py`): for anchor pairs within `max_len`, gates on
length, height difference, a **directional check** (each anchor's bearing to the
other must fall within one of its drop sectors, ± `SECTOR_TOL_DEG`), and
**exposure** (lower anchor's elevation minus the lowest terrain point strictly
between them, sampled along the line). Exposure is the highline's height.

**Zones** (`server/services/zones.py`): clusters paired anchors via union-find — pair
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
`server/router/serializers.py`). API bbox params accept either `bbox` (UTM) or
`bbox_lonlat`.

**Restrictions** (`etls/restriction/` builds/stores the layers,
`server/repositories/restrictions.py` reads them, `server/services/restrictions.py`
serves them, and the shared `LAYERS` registry lives in `core/restrictions.py`): informational protected-area overlays
covering all of Spain, built from MITECO's (national) Banco de Datos de la
Naturaleza files — Red Natura 2000 GML (INSPIRE ProtectedSites) and Espacios
Naturales Protegidos GeoJSON, each shipped as a peninsula+Baleares file and a
Canarias file in different CRSes. `just etl-restriction` downloads the raw
files into `data/spain/restrictions/raw/` through the country adapter
to derive three layers — `zepa` (Special Protection Area for Birds) and `zec`
(Site/Area of Community Importance), both filtered from the RN2000 GML by
designation code (parsed from the raw XML, since GDAL doesn't expose it as an
attribute), plus `enp` (Protected Natural Areas) from the ENP GeoJSON —
written to `data/spain/restrictions/<id>.parquet` and clipped to the viewport on
`GET /restrictions`. Tooltips are in English (the base/source-of-truth
language for restrictions text; see i18n below).

## Data layout (gitignored)

Both `data/` and `cache/` are partitioned by country at the top level (all
current data is `spain`); more countries slot in as sibling folders. The server
builds a filesystem index from `data/<country>/<region>/grid.json`; explicit
region requests use that index, including its on-disk country.

    data/<country>/<region>/grid.json                    {bbox, chunk_m, crs, dtm_source}
    data/<country>/<region>/anchors/p_{cx}_{cy}.parquet  anchors per chunk
    data/<country>/<region>/pairs/q_{cx}_{cy}.parquet    candidate pairs per chunk (exposure baked in)
    data/<country>/<region>/tiles/                       transient DTM tile cache, deleted once a chunk finishes
    data/<country>/<region>/density/z{z}.npz             zoomed-out density pyramid (optional, `etl-density-8`)
    data/<country>/restrictions/<id>.parquet             protected-area overlays (national per country)
    cache/<country>/mdt05_tiles/                         persistent CNIG MDT05 sheet cache (national, cross-region)
    cache/<country>/mdt05_sheet_index/                   cached CNIG sheet-index catalog queries

The `cache/` folder is a sibling of `data/` (not under it): it holds only
re-downloadable CNIG DTM sheets shared across a country's regions, so it can be
wiped without losing any precomputed output. `data/` holds derived results plus
the transient per-chunk `tiles/` scratch, deleted as each chunk finishes. The
server discovers regions by scanning `data/*/*/grid.json`, so region names must
stay unique across countries.

Every read endpoint takes a `country` query param that scopes it to one
partition, defaulting to `config.DEFAULT_COUNTRY` (`"spain"`) — the single
source of that default. `/regions` returns each region's `country` and lists
only the requested one; `/zones`, `/anchors` and `/density` only serve that
country's regions when no explicit `region` is given (an explicit `region`
uses its indexed filesystem country); `/restrictions` reads only
`data/<country>/restrictions/`. Existing callers that omit `country` keep
getting Spain unchanged.

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
- **`highliner/core/restrictions.py`** (the shared `LAYERS` registry) — the
  **English** restriction `label` / `tooltip` / `highlight`, served via
  `/restrictions`. This is the `en` source and the fallback for any layer
  without a translation.

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
