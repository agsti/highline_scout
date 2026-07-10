# Replace Catalonia restrictions with national MITECO layers — design

**Date:** 2026-07-10
**Status:** Awaiting review
**Builds on:** `2026-07-04-restriction-definitions-i18n-design.md`,
`SPAIN_PRECOMPUTE.md`, `NEW_LOCATIONS.md`.

## Goal

Extend the protected-area overlays beyond Catalonia to all of Spain by replacing
the three Generalitat layers (`pein` / `parcs` / `fauna`, sourced from the
`sig.gencat.cat` WFS) with three national layers derived from MITECO's Banco de
Datos de la Naturaleza:

    zepa   Zonas de Especial Protección para las Aves   (Red Natura 2000)
    zec    Lugares de Importancia Comunitaria / ZEC      (Red Natura 2000)
    enp    Espacios Naturales Protegidos                 (parques, reservas, …)

This gives a single uniform schema covering the whole country. The Generalitat
layers are dropped entirely (not clipped or kept alongside).

Restrictions are informational overlays only — they do not feed anchor/zone
detection. This change touches the fetch/transform, the layer registry, and the
i18n strings; it does not touch precompute, DTM, or CRS handling of the terrain
pipeline.

## Scope

- `highliner/repositories/restrictions.py` — the `LAYERS` registry and the
  fetch/transform pipeline.
- `justfile` — the `fetch-restrictions` recipe.
- `frontend/src/lib/i18n/restrictionStrings.ts` — the translated definitions.
- Tests referencing the old layer ids/strings.

## Non-goals

- No change to the serving layer (`highliner/services/restrictions.py`),
  routers, or the frontend controls/map/popups — those are data-driven off
  `GET /restrictions/layers` and adapt to whatever ids the registry exposes.
- No regional (autonomous-community) IDE sources. National MITECO only. Regional
  refinement is a possible future per-region pass, out of scope here.
- No seasonal climbing-closure / raptor-nesting calendar data — that lives in
  park management plans and federation calendars, not in these polygon layers,
  and remains a known data gap.
- No CRS/precompute changes. Restriction layers are stored in EPSG:4326
  independent of the terrain pipeline's projected CRS.

## Data source

MITECO publishes each dataset as a **single national bulk file**, updated
December 2025. Verified live on 2026-07-10 (real files return HTTP 206 to a
range request; guessed alternatives returned an identical 46,740-byte soft-404
HTML page at HTTP 200):

| Layer(s) | File | Format | URL |
|----------|------|--------|-----|
| `zepa`, `zec` | Red Natura 2000 | **GML** (INSPIRE PS) | `…/banco-datos-naturaleza/3-rn2000/PS.Natura2000_2025_gml.zip` |
| `enp` | Espacios Naturales Protegidos | **GeoJSON** | `…/banco-datos-naturaleza/enp/Enp2025_geojson.zip` |

Base: `https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/servicios`

Notes:
- RN2000 GeoJSON is **not** published; only GML. GeoPandas reads GML via
  pyogrio/fiona, so this is fine — the two derived layers just read a GML file
  instead of GeoJSON.
- The RN2000 file is one dataset holding both ZEPA and ZEC/LIC sites,
  distinguished by the INSPIRE Natura 2000 **site type**: SPA (=ZEPA),
  SCI/SAC (=LIC/ZEC), or type "both". A "both" site belongs to **both** derived
  layers. The exact field name/values are confirmed from the downloaded GML at
  implementation (INSPIRE `siteType` / Spanish schema equivalent).
- ENP holds 45+ protection figures (parques nacionales/naturales, reservas,
  monumentos, paisajes protegidos, …) collapsed into one `enp` layer.
- Source CRS confirmed from each file at implementation and reprojected to
  EPSG:4326 if needed (INSPIRE GML is typically EPSG:4258 ≈ WGS84; GeoJSON is
  EPSG:4326 by spec). The Catalonia WFS served 4326 directly and needed no
  reprojection; these may.
- License: free reuse with attribution to MITECO as author/owner.

## Architecture

Split the old single-command flow (`highliner fetch-restrictions` →
`fetch_all()` downloads from WFS + transforms + writes parquet) into a **download
step** and a **transform step**, so the raw national files are downloaded once
into `data/` and never re-fetched on rebuilds.

### Download step (`just fetch-restrictions`)

The `just` recipe downloads the two national files into
`data/restrictions/raw/` if they are not already present (idempotent —
"download once"), unzips them, then invokes the transform. Sketch:

```make
fetch-restrictions:
    mkdir -p data/restrictions/raw
    test -f data/restrictions/raw/rn2000.gml \
      || (curl -fL "$RN2000_URL" -o data/restrictions/raw/rn2000_gml.zip \
          && unzip -o -j data/restrictions/raw/rn2000_gml.zip -d data/restrictions/raw)
    test -f data/restrictions/raw/enp.geojson \
      || (curl -fL "$ENP_URL" -o data/restrictions/raw/enp_geojson.zip \
          && unzip -o -j data/restrictions/raw/enp_geojson.zip -d data/restrictions/raw)
    uv run highliner fetch-restrictions
```

(Exact unzipped filenames normalized to stable names — `rn2000.gml`,
`enp.geojson` — during implementation once the archive contents are known.)

### Transform step (`highliner/repositories/restrictions.py`)

- `_fetch_source(feature_type)` (paginate-a-WFS) → replaced by
  `_load_source(path)`: read a local GML/GeoJSON with GeoPandas, reproject to
  EPSG:4326 if the source CRS differs, return the GeoDataFrame. No network
  access from Python.
- `LAYERS` registry rewritten: three specs (`zepa`, `zec`, `enp`). Each spec
  names its source **file** (rn2000 / enp), a `keep` predicate over the
  site-type / figure attribute, the `name_field` for the official site name,
  and English `label` / `tooltip` / `highlight` text.
- `build_layer` keeps its shape (filter via `keep`, normalize `name`, simplify
  with `SIMPLIFY_TOL_DEG`), reading from the loaded source GeoDataFrame instead
  of a list of GeoJSON feature dicts. The `source_cache` still dedups the shared
  RN2000 read across the `zepa` and `zec` layers.
- `fetch_all` unchanged in contract: iterate `LAYERS`, write
  `data/restrictions/<id>.parquet`.
- `load_layer` unchanged.

The `WFS`, `_NS`, `_PAGE`, `_HEADERS` constants and the pagination loop are
removed.

## i18n — English base, es/ca overrides

The base language flips from Catalan to English (English needs no translation,
is what a no-preference crawler sees, and is a sensible SEO default).

- **Server** (`LAYERS` tooltips) written in **English**. `GET
  /restrictions/layers` serves English `label`/`tooltip`/`highlight`.
- **Frontend** (`restrictionStrings.ts`): provide `es` and `ca` entries for the
  new ids; `en` has no entry and falls back to the server text. Same resolver
  `restrictionText(id, lang, fallback)` and the same rule that each language's
  `highlight` is a verbatim substring of its `tooltip` (for `appendDescText`'s
  `indexOf`).
- Remove `pein` / `parcs` / `fauna` from both server and frontend. Add
  `zepa` / `zec` / `enp`.
- English works standalone; `es` and `ca` translations layer on top and can land
  incrementally.

Draft layer text (final wording refined during implementation), highlight
clause in **bold**:

- **zepa** — "Special Protection Area for Birds (Red Natura 2000, Birds
  Directive). **Cliffs here commonly have seasonal climbing/access closures for
  raptor nesting (roughly winter–summer, varies by site); check the managing
  body before rigging.**"
- **zec** — "Site of Community Importance / Special Area of Conservation (Red
  Natura 2000, Habitats Directive). **Activities that may harm the protected
  habitats can be regulated or require an impact assessment.**"
- **enp** — "Protected Natural Area (national/regional figure — nature park,
  reserve, natural monument, …), each with its own management plan.
  **Climbing, bivouacking, drones and organized events are often regulated and
  may need authorization from the managing body.**"

## Attribution

MITECO's license requires crediting them as author/owner. A short data-source
credit ("Protected-area data © MITECO") is surfaced in the layer panel or map
footer. Low-effort; exact placement decided during implementation.

## Testing

- **Backend** — unit-test `build_layer` against a small fixture holding a
  couple of SPA, SCI, "both", and ENP features in a non-4326 CRS. Assert: each
  derived layer keeps the right rows (including "both" appearing in both `zepa`
  and `zec`), `name` normalized from the official name field, output CRS is
  EPSG:4326. Test `_load_source` reads GML and GeoJSON fixtures.
- **Frontend** — update `i18n.test.tsx` for the new ids and the English-base
  fallback direction (en → server text; es/ca → overrides).
- Existing tests referencing `pein`/`parcs`/`fauna` updated to the new ids.

## Open items confirmed at implementation

1. Exact RN2000 site-type field name/values in the GML (INSPIRE `siteType` vs
   Spanish schema) and the ENP figure field.
2. The official site-name attribute → `name` for each dataset.
3. Source CRS of each file (reproject to 4326 if needed).
4. Unzipped filenames inside each archive (normalized to `rn2000.gml` /
   `enp.geojson`).
