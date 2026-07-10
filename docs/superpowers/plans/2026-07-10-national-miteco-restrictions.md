# National MITECO Restrictions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Catalonia's three Generalitat protected-area layers (`pein`/`parcs`/`fauna`) with three national MITECO layers (`zepa`/`zec`/`enp`) covering all of Spain, fetched via a `just` recipe that downloads national files once into `data/` and transformed locally.

**Architecture:** A `just fetch-restrictions` recipe downloads two national bulk files (RN2000 GML, ENP GeoJSON) into `data/restrictions/raw/` idempotently, unzips them, then runs the Python transform. The transform (`highliner/repositories/restrictions.py`) reads the local files with GeoPandas, reprojects to EPSG:4326, splits/filters them into the three derived layers via the `LAYERS` registry, and writes `data/restrictions/<id>.parquet`. The serving layer and frontend controls are data-driven off `GET /restrictions/layers` and need no logic change — only the layer ids/strings change. i18n base language flips from Catalan to English.

**Tech Stack:** Python 3.12, GeoPandas (+ pyogrio/GDAL for GML), Shapely, FastAPI; React + TypeScript + Vitest frontend; `just`, `uv`, `curl`, `unzip`.

## Global Constraints

- Package/run tooling: `uv` with managed Python 3.12 (the plain venv is broken). Run Python via `uv run ...`.
- Restriction layers are stored and served in **EPSG:4326** (lon/lat), independent of the terrain pipeline's projected CRS.
- Each language's `highlight` string MUST be a verbatim substring of that language's `tooltip` (the frontend locates it with `indexOf` in `appendDescText`).
- i18n base language is **English**: server (`LAYERS`) text is English; `restrictionStrings.ts` provides `es` + `ca` overrides only; `en` falls back to the server text.
- Layer geometry is simplified with the existing `SIMPLIFY_TOL_DEG = 0.0001`.
- Verified-live source URLs (2026-07-10), base `https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/servicios/banco-datos-naturaleza`:
  - RN2000 (GML): `/3-rn2000/PS.Natura2000_2025_gml.zip`
  - ENP (GeoJSON): `/enp/Enp2025_geojson.zip`
- Work on a feature branch (we start on `main`): `git checkout -b feat/national-restrictions` before Task 1.
- Attribution: MITECO must be credited as data author/owner somewhere user-visible.

---

### Task 1: Download recipe + raw-file schema discovery

Downloads the national files once and records the actual attribute field names and type values the later tasks depend on. This is a scaffolding/discovery task; its "test" is running the recipe and the inspection command and recording their output into this plan's constants.

**Files:**
- Modify: `justfile` (the `fetch-restrictions` recipe, currently at `justfile:48-50`)
- Create: `scripts/inspect_restrictions_raw.py` (throwaway inspection helper)

**Interfaces:**
- Produces: `data/restrictions/raw/` containing one `*.gml` (RN2000) and one `*.geojson`/`*.json` (ENP) file; and the four discovered constants recorded in Task 3 (`RN2000_TYPE_FIELD`, `RN2000_NAME_FIELD`, `ENP_NAME_FIELD`, and the ZEPA/ZEC type value sets).

- [ ] **Step 1: Create the feature branch**

```bash
git checkout -b feat/national-restrictions
```

- [ ] **Step 2: Rewrite the `fetch-restrictions` recipe in `justfile`**

Replace the current recipe (`justfile:48-50`) with a download-once-then-transform recipe:

```make
# Download national protected-area files (once) into data/restrictions/raw/
# and transform them into data/restrictions/<id>.parquet.
RN2000_URL := "https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/servicios/banco-datos-naturaleza/3-rn2000/PS.Natura2000_2025_gml.zip"
ENP_URL := "https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/servicios/banco-datos-naturaleza/enp/Enp2025_geojson.zip"

fetch-restrictions:
    mkdir -p data/restrictions/raw
    ls data/restrictions/raw/*.gml >/dev/null 2>&1 || \
      (curl -fL "{{RN2000_URL}}" -o data/restrictions/raw/rn2000.zip && \
       unzip -o -j data/restrictions/raw/rn2000.zip -d data/restrictions/raw && \
       rm data/restrictions/raw/rn2000.zip)
    ls data/restrictions/raw/*.geojson data/restrictions/raw/*.json >/dev/null 2>&1 || \
      (curl -fL "{{ENP_URL}}" -o data/restrictions/raw/enp.zip && \
       unzip -o -j data/restrictions/raw/enp.zip -d data/restrictions/raw && \
       rm data/restrictions/raw/enp.zip)
    uv run highliner fetch-restrictions
```

- [ ] **Step 3: Add `data/restrictions/raw/` to `.gitignore`**

Confirm `data/` (or `data/restrictions/`) is already git-ignored; if not, append `data/restrictions/raw/` to `.gitignore`. The raw downloads and derived parquet are build artifacts, not committed.

- [ ] **Step 4: Download the raw files**

Run: `just fetch-restrictions` — expect it to fail at the final `uv run highliner fetch-restrictions` step (the transform still targets the old WFS code). That's fine; the goal here is the downloaded files. Verify:

```bash
ls -la data/restrictions/raw/
```
Expected: at least one `*.gml` file and one `*.geojson` (or `*.json`) file present.

- [ ] **Step 5: Write the inspection helper**

Create `scripts/inspect_restrictions_raw.py`:

```python
"""Print columns, CRS, and candidate type/name fields of the raw MITECO files.

Throwaway helper used once to discover the attribute schema the LAYERS registry
depends on. Safe to delete after the constants are recorded in the plan.
"""
import glob
import geopandas as gpd

for pattern in ("data/restrictions/raw/*.gml", "data/restrictions/raw/*.geojson",
                "data/restrictions/raw/*.json"):
    for path in glob.glob(pattern):
        gdf = gpd.read_file(path, rows=50)
        print(f"\n=== {path} ===")
        print("CRS:", gdf.crs)
        print("columns:", list(gdf.columns))
        for col in gdf.columns:
            if gdf[col].dtype == object and col != "geometry":
                vals = gdf[col].dropna().unique()[:8]
                print(f"  {col!r} sample: {list(vals)}")
```

- [ ] **Step 6: Run the inspection and record the schema**

Run: `uv run python scripts/inspect_restrictions_raw.py`

From the output, record and carry into Task 3:
- **`RN2000_TYPE_FIELD`** — the field in the GML that distinguishes ZEPA vs LIC/ZEC. Expected: an INSPIRE site-type field. Under the INSPIRE/BDN convention values are `A` (SPA→ZEPA), `B` (SCI/SAC→ZEC/LIC), `C` (both). If instead the field holds strings like `ZEPA`/`LIC`/`ZEC`, note the exact strings.
- **ZEPA/ZEC value sets** — from the observed values: ZEPA = the SPA value(s) plus the "both" value; ZEC = the SCI/SAC value(s) plus the "both" value.
- **`RN2000_NAME_FIELD`** — the official site-name column (e.g. `SITE_NAME`, `NOMBRE`, `NOM`).
- **`ENP_NAME_FIELD`** — the ENP site-name column.
- Confirm each file's **CRS** (to know whether reprojection to 4326 is needed).

- [ ] **Step 7: Commit**

```bash
git add justfile scripts/inspect_restrictions_raw.py .gitignore
git commit -m "chore: national MITECO restriction download recipe + schema inspector"
```

---

### Task 2: `_load_source` — read local files, reproject to 4326

**Files:**
- Modify: `highliner/repositories/restrictions.py`
- Test: `tests/test_restrictions.py` (create)

**Interfaces:**
- Consumes: raw files under `data/restrictions/raw/` from Task 1.
- Produces:
  - `RAW_DIR: Path` — `Path(config.DATA_DIR) / "restrictions" / "raw"`.
  - `SOURCE_GLOBS: dict[str, tuple[str, ...]]` — `{"rn2000": ("*.gml",), "enp": ("*.geojson", "*.json")}`.
  - `_load_source(source_key: str, raw_dir: Path | None = None) -> gpd.GeoDataFrame` — reads the first file matching the source's globs, reprojects to EPSG:4326, returns it. Raises `FileNotFoundError` if no file matches.

- [ ] **Step 1: Write the failing test**

Create `tests/test_restrictions.py`:

```python
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from highliner.repositories import restrictions as R


def _write_geojson(path: Path, epsg: int) -> None:
    gdf = gpd.GeoDataFrame(
        {"NOMBRE": ["A"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    ).to_crs(epsg)
    gdf.to_file(path, driver="GeoJSON")


def test_load_source_reprojects_to_4326(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_geojson(raw / "enp.geojson", epsg=25830)

    gdf = R._load_source("enp", raw_dir=raw)

    assert gdf.crs is not None
    assert gdf.crs.to_epsg() == 4326
    assert len(gdf) == 1


def test_load_source_missing_raises(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    import pytest
    with pytest.raises(FileNotFoundError):
        R._load_source("enp", raw_dir=raw)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_restrictions.py -v`
Expected: FAIL — `AttributeError: module has no attribute '_load_source'` (and `RAW_DIR`/`SOURCE_GLOBS` missing).

- [ ] **Step 3: Implement `_load_source`**

In `highliner/repositories/restrictions.py`, remove the WFS constants (`WFS`, `_NS`, `_PAGE`, `_HEADERS`) and the `_fetch_source` function, and add near the top (after imports):

```python
RAW_DIR = Path(config.DATA_DIR) / "restrictions" / "raw"
SOURCE_GLOBS: dict[str, tuple[str, ...]] = {
    "rn2000": ("*.gml",),
    "enp": ("*.geojson", "*.json"),
}


def _load_source(source_key: str, raw_dir: Path | None = None) -> gpd.GeoDataFrame:
    """Read the first raw file matching ``source_key``'s globs and return it in
    EPSG:4326. Raw files are placed by the ``just fetch-restrictions`` recipe."""
    base = raw_dir if raw_dir is not None else RAW_DIR
    for pattern in SOURCE_GLOBS[source_key]:
        matches = sorted(base.glob(pattern))
        if matches:
            gdf = gpd.read_file(matches[0])
            if gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")
            elif gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs("EPSG:4326")
            return gdf
    raise FileNotFoundError(
        f"no raw file for source {source_key!r} in {base} "
        f"(run `just fetch-restrictions`)")
```

Keep the existing `import requests` only if still used elsewhere; otherwise remove it and drop `requests`/`types-requests` from `pyproject.toml` if no other module imports it (check with `rg -l "import requests" highliner/`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_restrictions.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add highliner/repositories/restrictions.py tests/test_restrictions.py
git commit -m "feat: read local MITECO source files, reproject to 4326"
```

---

### Task 3: Rewrite `LAYERS` registry + `build_layer` for the three national layers

**Files:**
- Modify: `highliner/repositories/restrictions.py`
- Test: `tests/test_restrictions.py`

**Interfaces:**
- Consumes: `_load_source` from Task 2.
- Produces:
  - `LAYERS: dict[str, LayerSpec]` keyed by `"zepa"`, `"zec"`, `"enp"`, each with `label`, `color`, `source` (key into `SOURCE_GLOBS`), `name_field`, `keep: Callable[[Mapping[str, Any]], bool]`, `tooltip`, `highlight` (English).
  - `build_layer(layer_id: str, source_cache: dict[str, gpd.GeoDataFrame]) -> gpd.GeoDataFrame` — filters the source by `keep`, normalizes `name`, simplifies, returns a 4326 GeoDataFrame with columns `["name", "geometry"]`.

> Set the four discovery constants below from **Task 1 Step 6** output before implementing. Values shown are the expected INSPIRE/BDN convention; adjust to what the inspector actually printed.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_restrictions.py`:

```python
def _rn2000_fixture() -> gpd.GeoDataFrame:
    poly = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    return gpd.GeoDataFrame(
        {
            R.RN2000_TYPE_FIELD: ["A", "B", "C"],  # SPA, SCI, both
            R.RN2000_NAME_FIELD: ["Birds Site", "Habitat Site", "Both Site"],
        },
        geometry=[poly, poly, poly],
        crs="EPSG:4326",
    )


def test_build_zepa_keeps_spa_and_both(monkeypatch) -> None:
    src = _rn2000_fixture()
    cache = {"rn2000": src}
    gdf = R.build_layer("zepa", cache)
    assert sorted(gdf["name"]) == ["Birds Site", "Both Site"]
    assert gdf.crs.to_epsg() == 4326


def test_build_zec_keeps_sci_and_both() -> None:
    src = _rn2000_fixture()
    gdf = R.build_layer("zec", {"rn2000": src})
    assert sorted(gdf["name"]) == ["Both Site", "Habitat Site"]


def test_build_enp_keeps_all_and_normalizes_name() -> None:
    poly = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    src = gpd.GeoDataFrame(
        {R.ENP_NAME_FIELD: ["  Park  ", None]},
        geometry=[poly, poly],
        crs="EPSG:4326",
    )
    gdf = R.build_layer("enp", {"enp": src})
    assert sorted(gdf["name"]) == ["", "Park"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_restrictions.py -k build -v`
Expected: FAIL — `RN2000_TYPE_FIELD` / new `LAYERS` shape not present.

- [ ] **Step 3: Implement the registry and `build_layer`**

Replace the old `LAYERS` dict and `build_layer` in `highliner/repositories/restrictions.py`. Add the discovery constants and update `LayerSpec.keep` typing:

```python
from collections.abc import Mapping

# --- Discovery constants (set from Task 1 inspection) -----------------------
RN2000_TYPE_FIELD = "SITE_TYPE"     # INSPIRE site type: A=SPA, B=SCI/SAC, C=both
RN2000_NAME_FIELD = "SITE_NAME"     # official RN2000 site name column
ENP_NAME_FIELD = "SITE_NAME"        # official ENP site name column
_ZEPA_TYPES = {"A", "C"}
_ZEC_TYPES = {"B", "C"}
# ---------------------------------------------------------------------------


class LayerSpec(TypedDict):
    label: str
    color: str
    source: str
    name_field: str
    keep: Callable[[Mapping[str, Any]], bool]
    tooltip: str
    highlight: str


LAYERS: dict[str, LayerSpec] = {
    "zepa": {
        "label": "ZEPA (Birds)",
        "color": "#e31a1c",
        "source": "rn2000",
        "name_field": RN2000_NAME_FIELD,
        "keep": lambda p: str(p.get(RN2000_TYPE_FIELD) or "").strip() in _ZEPA_TYPES,
        "tooltip": ("Special Protection Area for Birds - Red Natura 2000 (EU "
                    "Birds Directive). Cliffs in these areas commonly have "
                    "seasonal climbing and access closures for raptor nesting "
                    "(roughly winter to summer, varies by site); check with the "
                    "managing body before rigging."),
        "highlight": ("Cliffs in these areas commonly have seasonal climbing and "
                      "access closures for raptor nesting (roughly winter to "
                      "summer, varies by site); check with the managing body "
                      "before rigging."),
    },
    "zec": {
        "label": "ZEC / LIC",
        "color": "#ff7f00",
        "source": "rn2000",
        "name_field": RN2000_NAME_FIELD,
        "keep": lambda p: str(p.get(RN2000_TYPE_FIELD) or "").strip() in _ZEC_TYPES,
        "tooltip": ("Site of Community Importance / Special Area of Conservation "
                    "- Red Natura 2000 (EU Habitats Directive). Activities that "
                    "may harm the protected habitats can be regulated and may "
                    "require an environmental impact assessment."),
        "highlight": ("Activities that may harm the protected habitats can be "
                      "regulated and may require an environmental impact "
                      "assessment."),
    },
    "enp": {
        "label": "Protected Natural Areas",
        "color": "#6a3d9a",
        "source": "enp",
        "name_field": ENP_NAME_FIELD,
        "keep": lambda p: True,
        "tooltip": ("Protected Natural Area - a national or regional protection "
                    "figure such as a national or nature park, nature reserve or "
                    "natural monument, each with its own management plan. "
                    "Climbing, bivouacking, drones and organized events are often "
                    "regulated and may need authorization from the managing "
                    "body."),
        "highlight": ("Climbing, bivouacking, drones and organized events are "
                      "often regulated and may need authorization from the "
                      "managing body."),
    },
}


def build_layer(layer_id: str,
                source_cache: dict[str, gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    """Filter/normalize/simplify a loaded source into a derived overlay layer."""
    spec = LAYERS[layer_id]
    src = source_cache.get(spec["source"])
    if src is None:
        src = source_cache[spec["source"]] = _load_source(spec["source"])
    keep = spec["keep"]
    mask = src.apply(lambda row: keep(row), axis=1)
    sub = src[mask]
    names = (sub[spec["name_field"]].fillna("").astype(str).str.strip()
             if len(sub) else [])
    gdf = gpd.GeoDataFrame({"name": list(names)},
                           geometry=list(sub.geometry), crs="EPSG:4326")
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_TOL_DEG,
                                            preserve_topology=True)
    return gdf
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_restrictions.py -v`
Expected: PASS (all Task 2 + Task 3 tests).

- [ ] **Step 5: Typecheck**

Run: `uv run mypy`
Expected: no errors (strict mypy is enforced in this repo).

- [ ] **Step 6: Commit**

```bash
git add highliner/repositories/restrictions.py tests/test_restrictions.py
git commit -m "feat: national zepa/zec/enp layer registry + build_layer"
```

---

### Task 4: Update `fetch_all`, the CLI message, and the API registry test

**Files:**
- Modify: `highliner/repositories/restrictions.py` (`fetch_all` docstring/print only)
- Modify: `highliner/cli.py:60-63` (`_cmd_fetch_restrictions` message)
- Modify: `tests/test_api.py:161-218` (restriction tests → new ids)

**Interfaces:**
- Consumes: `LAYERS`, `build_layer` from Task 3.
- Produces: `data/restrictions/{zepa,zec,enp}.parquet` when run end-to-end.

- [ ] **Step 1: Update the failing API test to the new ids**

In `tests/test_api.py`, change the registry assertion (`test_restriction_layers_registry`) from:

```python
    assert {"pein", "parcs", "fauna"} <= ids
    pein = next(row for row in layers if row["id"] == "pein")
    assert pein["label"] and pein["color"].startswith("#")
```
to:
```python
    assert {"zepa", "zec", "enp"} <= ids
    zepa = next(row for row in layers if row["id"] == "zepa")
    assert zepa["label"] and zepa["color"].startswith("#")
```

In `test_restrictions_in_view` and `test_restrictions_filters_out_of_view`, replace every `"pein"` literal (the `_write_restriction_layer(...)` id, the `layers=` param, and the `props["layer"] == "pein"` assertion) with `"zepa"`.

- [ ] **Step 2: Run the API tests to verify they fail**

Run: `uv run pytest tests/test_api.py -k restriction -v`
Expected: FAIL — server still serves `pein`/`parcs`/`fauna` (old registry) OR passes only after Task 3 is merged; the registry test fails on the id set.

> Note: if Task 3 is already merged, `test_restriction_layers_registry` passes immediately (registry already returns the new ids) and only the `_write_restriction_layer`-based tests needed the id rename — that is expected; proceed.

- [ ] **Step 3: Update `fetch_all` message and CLI text**

In `highliner/repositories/restrictions.py`, update the `fetch_all` docstring to say it reads local national files (not WFS). In `highliner/cli.py:62`, change:

```python
    print("Downloading protected-area layers from the Generalitat WFS...")
```
to:
```python
    print("Building national protected-area layers from data/restrictions/raw/ ...")
```

- [ ] **Step 4: Run the API tests to verify they pass**

Run: `uv run pytest tests/test_api.py -k restriction -v`
Expected: PASS.

- [ ] **Step 5: Full end-to-end build (integration check)**

Run: `just fetch-restrictions`
Expected: downloads (or skips) raw files, then prints one line per layer (`zepa`, `zec`, `enp`) with a feature count and KiB size, writing `data/restrictions/{zepa,zec,enp}.parquet`. Sanity-check counts are plausible (hundreds–low thousands of features each; `zepa` and `zec` non-empty, `enp` largest).

- [ ] **Step 6: Delete the throwaway inspector and commit**

```bash
rm scripts/inspect_restrictions_raw.py
git add highliner/repositories/restrictions.py highliner/cli.py tests/test_api.py scripts/inspect_restrictions_raw.py
git commit -m "feat: wire national restriction build end-to-end; update CLI + api tests"
```

---

### Task 5: Frontend i18n — English base, es/ca overrides for new ids

**Files:**
- Modify: `frontend/src/lib/i18n/restrictionStrings.ts`
- Modify: `frontend/src/lib/i18n/i18n.test.tsx`
- Modify: `frontend/src/components/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `restrictionText(id, lang, fallback)` (unchanged resolver).
- Produces: `RESTRICTION_STRINGS` with top-level keys `es` and `ca` (no `en`), each holding `zepa`/`zec`/`enp` entries of `{ label, tooltip, highlight }`.

- [ ] **Step 1: Rewrite `restrictionStrings.ts`**

Replace the `RESTRICTION_STRINGS` object body (keep the `import`, the `RestrictionText` interface, and the `restrictionText` resolver at the bottom unchanged) with:

```typescript
export const RESTRICTION_STRINGS: Partial<Record<Lang, Record<string, RestrictionText>>> = {
  es: {
    zepa: {
      label: "ZEPA (Aves)",
      tooltip:
        "Zona de Especial Protección para las Aves — Red Natura 2000 (Directiva Aves). Los cortados de estas zonas suelen tener cierres estacionales de escalada y acceso por la nidificación de rapaces (aprox. de invierno a verano, varía según el espacio); consulta al órgano gestor antes de instalar.",
      highlight:
        "Los cortados de estas zonas suelen tener cierres estacionales de escalada y acceso por la nidificación de rapaces (aprox. de invierno a verano, varía según el espacio); consulta al órgano gestor antes de instalar.",
    },
    zec: {
      label: "ZEC / LIC",
      tooltip:
        "Lugar de Importancia Comunitaria / Zona Especial de Conservación — Red Natura 2000 (Directiva Hábitats). Las actividades que puedan dañar los hábitats protegidos pueden estar reguladas y requerir evaluación de impacto ambiental.",
      highlight:
        "Las actividades que puedan dañar los hábitats protegidos pueden estar reguladas y requerir evaluación de impacto ambiental.",
    },
    enp: {
      label: "Espacios Naturales Protegidos",
      tooltip:
        "Espacio Natural Protegido — una figura de protección estatal o autonómica como un parque nacional o natural, una reserva natural o un monumento natural, cada uno con su propio plan de gestión. La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
      highlight:
        "La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
    },
  },
  ca: {
    zepa: {
      label: "ZEPA (Aus)",
      tooltip:
        "Zona d'Especial Protecció per a les Aus — Xarxa Natura 2000 (Directiva Aus). Els cingles d'aquestes zones sovint tenen tancaments estacionals d'escalada i accés per la nidificació de rapinyaires (aprox. d'hivern a estiu, varia segons l'espai); consulteu l'òrgan gestor abans d'instal·lar.",
      highlight:
        "Els cingles d'aquestes zones sovint tenen tancaments estacionals d'escalada i accés per la nidificació de rapinyaires (aprox. d'hivern a estiu, varia segons l'espai); consulteu l'òrgan gestor abans d'instal·lar.",
    },
    zec: {
      label: "ZEC / LIC",
      tooltip:
        "Lloc d'Importància Comunitària / Zona Especial de Conservació — Xarxa Natura 2000 (Directiva Hàbitats). Les activitats que puguin malmetre els hàbitats protegits poden estar regulades i requerir avaluació d'impacte ambiental.",
      highlight:
        "Les activitats que puguin malmetre els hàbitats protegits poden estar regulades i requerir avaluació d'impacte ambiental.",
    },
    enp: {
      label: "Espais Naturals Protegits",
      tooltip:
        "Espai Natural Protegit — una figura de protecció estatal o autonòmica com un parc nacional o natural, una reserva natural o un monument natural, cadascun amb el seu pla de gestió. L'escalada, el vivac, els drons i els actes organitzats sovint estan regulats i poden necessitar autorització de l'òrgan gestor.",
      highlight:
        "L'escalada, el vivac, els drons i els actes organitzats sovint estan regulats i poden necessitar autorització de l'òrgan gestor.",
    },
  },
};
```

- [ ] **Step 2: Update `i18n.test.tsx` restriction assertions**

The test at `frontend/src/lib/i18n/i18n.test.tsx:53-95` uses old ids (`pein`, `fauna`) and assumed Catalan-base semantics. Update:
- The substring-invariant loop (lines ~60-66) is id-agnostic — it iterates `RESTRICTION_STRINGS` — leave its logic, it now covers `es`/`ca`.
- The "falls back for the base language" case: change the base-language check so that **`en`** returns the fallback (English is now the server base):

```typescript
  it("falls back to the server text for the base language (en)", () => {
    const fallback = { label: "L", tooltip: "T", highlight: "T" };
    expect(restrictionText("zepa", "en", fallback)).toEqual(fallback);
  });
```
- Replace the representative-text assertions (the `restrictionText("pein", "es", ...)` / `restrictionText("fauna", "en", ...)` cases) with `zepa`/`enp` in `es`/`ca`, asserting the exact strings from Step 1, e.g.:

```typescript
  it("returns the Spanish override for a known layer", () => {
    const fallback = { label: "L", tooltip: "T", highlight: "T" };
    expect(restrictionText("enp", "es", fallback)).toEqual({
      label: "Espacios Naturales Protegidos",
      tooltip:
        "Espacio Natural Protegido — una figura de protección estatal o autonómica como un parque nacional o natural, una reserva natural o un monumento natural, cada uno con su propio plan de gestión. La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
      highlight:
        "La escalada, el vivac, los drones y los actos organizados suelen estar regulados y pueden necesitar autorización del órgano gestor.",
    });
  });
```

- [ ] **Step 3: Update `MapView.test.tsx` layer id**

In `frontend/src/components/map/MapView.test.tsx`, the restriction fixtures use `id: "pein"` / `layer: "pein"` / `enabledRestrictions: ["pein"]` (shown as `"n"` earlier due to a grep replace). Change those literals to `"zepa"` and the `label: "PEIN"` fixture to `label: "ZEPA (Birds)"` so it reflects the new registry. These are opaque string fixtures; the component logic is unaffected.

- [ ] **Step 4: Run the frontend tests**

Run: `cd frontend && npm test`
Expected: PASS. In particular the substring-invariant test passes (every `es`/`ca` `highlight` is a substring of its `tooltip`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/i18n/restrictionStrings.ts frontend/src/lib/i18n/i18n.test.tsx frontend/src/components/map/MapView.test.tsx
git commit -m "feat: national restriction i18n (English base, es/ca overrides)"
```

---

### Task 6: MITECO attribution credit

**Files:**
- Modify: `frontend/src/lib/i18n/strings.ts` (add a credit string key)
- Modify: the restriction panel component `frontend/src/components/RestrictionLayerControls.tsx` (render the credit)
- Test: `frontend/src/components/AppShell.test.tsx` or the controls' own test

**Interfaces:**
- Consumes: the existing `STRINGS`/`useI18n()` machinery.
- Produces: a visible "Protected-area data © MITECO" line under the restriction layer controls.

- [ ] **Step 1: Add the credit string**

In `frontend/src/lib/i18n/strings.ts`, add a key to each language's `STRINGS` entry (find the existing per-language object shape and match it), e.g. `restrictionCredit`:
- en: `"Protected-area data © MITECO"`
- es: `"Datos de espacios protegidos © MITECO"`
- ca: `"Dades d'espais protegits © MITECO"`

- [ ] **Step 2: Write/extend the failing test**

In the restriction controls' test (create `frontend/src/components/RestrictionLayerControls.test.tsx` if none exists, mirroring an existing component test's setup), assert the credit renders:

```typescript
it("shows the MITECO data attribution", () => {
  render(<RestrictionLayerControls {/* existing required props from a sibling test */} />);
  expect(screen.getByText(/© MITECO/)).toBeInTheDocument();
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd frontend && npm test -- RestrictionLayerControls`
Expected: FAIL — credit not rendered.

- [ ] **Step 4: Render the credit**

In `frontend/src/components/RestrictionLayerControls.tsx`, add a small muted line after the list of layer toggles:

```tsx
<p className="text-xs text-muted-foreground mt-2">{t.restrictionCredit}</p>
```
(Use the component's existing i18n accessor — match how sibling strings are read, e.g. `const { t } = useI18n()` or the project's equivalent.)

- [ ] **Step 5: Run to verify it passes**

Run: `cd frontend && npm test -- RestrictionLayerControls`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/i18n/strings.ts frontend/src/components/RestrictionLayerControls.tsx frontend/src/components/RestrictionLayerControls.test.tsx
git commit -m "feat: MITECO attribution credit in restriction panel"
```

---

### Task 7: Full verification + docs

**Files:**
- Modify: `AGENTS.md` (restrictions section — source is now national MITECO, not Generalitat WFS)
- Modify: `NEW_LOCATIONS.md` if it references the old `zec/zepa/pein/parcs/fauna` split (it does — update the layer list)

- [ ] **Step 1: Backend suite**

Run: `uv run pytest`
Expected: all pass (including `tests/test_restrictions.py`, `tests/test_api.py`).

- [ ] **Step 2: Typecheck**

Run: `uv run mypy`
Expected: no errors.

- [ ] **Step 3: Frontend suite**

Run: `cd frontend && npm test`
Expected: all pass.

- [ ] **Step 4: Manual smoke**

Run `just dev` and `just dev-web`, open the map, toggle the `ZEPA (Birds)` / `ZEC / LIC` / `Protected Natural Areas` layers over a non-Catalan cliff area (e.g. Riglos ~ `-0.53, 42.34` or El Chorro ~ `-4.77, 36.90`), confirm polygons render and popups show the site name + English tooltip; switch UI language to es/ca and confirm the tooltip text changes and the credit line updates.

- [ ] **Step 5: Update docs**

In `AGENTS.md`, update the restrictions description: source is MITECO's Banco de Datos de la Naturaleza national files (RN2000 GML + ENP GeoJSON) downloaded by `just fetch-restrictions`, layers `zepa`/`zec`/`enp`, English-base i18n. In `NEW_LOCATIONS.md`, replace the `zec/zepa/pein/parcs/fauna` example split reference with the current `zepa/zec/enp` national layers.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md NEW_LOCATIONS.md
git commit -m "docs: national MITECO restrictions in AGENTS.md and NEW_LOCATIONS.md"
```

---

## Notes for the implementer

- The four discovery constants (`RN2000_TYPE_FIELD`, `RN2000_NAME_FIELD`, `ENP_NAME_FIELD`, and the `_ZEPA_TYPES`/`_ZEC_TYPES` value sets) are the only values not knowable ahead of downloading the data. Task 1 Step 6 records them from the real files; every later task uses them by name. Do Task 1 first and do not guess.
- If GeoPandas cannot read the GML (`pyogrio`/GDAL missing the GML driver), the fallback is to add `pyogrio` explicitly to `pyproject.toml` dev/runtime deps, or convert the GML to GeoJSON in the `just` recipe with `ogr2ogr`. Check `uv run python -c "import pyogrio; print(pyogrio.__gdal_version__)"` first.
- `zepa` and `zec` share the `rn2000` source; `build_layer`'s `source_cache` reads it once across both — do not load it twice.
```
