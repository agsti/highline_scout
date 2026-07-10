# National MITECO Restrictions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Catalonia's three Generalitat protected-area layers (`pein`/`parcs`/`fauna`) with three national MITECO layers (`zepa`/`zec`/`enp`) covering all of Spain, fetched via a `just` recipe that downloads national files once into `data/` and transformed locally.

**Architecture:** A `just fetch-restrictions` recipe downloads the national bulk files (RN2000 GML + ENP GeoJSON, each split into a peninsula+baleares file and a canarias file) into `data/restrictions/raw/` idempotently, unzips them, then runs the Python transform. The transform (`highliner/repositories/restrictions.py`) reads every local file with GeoPandas, reprojects each to EPSG:4326, concatenates, splits/filters them into the three derived layers via the `LAYERS` registry, and writes `data/restrictions/<id>.parquet`. The serving layer and frontend controls are data-driven off `GET /restrictions/layers` and need no logic change — only the layer ids/strings change. i18n base language flips from Catalan to English.

**Tech Stack:** Python 3.12, GeoPandas (+ pyogrio/GDAL for GML), Shapely, `xml.etree.ElementTree`, pandas, FastAPI; React + TypeScript + Vitest frontend; `just`, `uv`, `curl`, `unzip`.

## Global Constraints

- Package/run tooling: `uv` with managed Python 3.12 (the plain venv is broken). Run Python via `uv run ...`.
- Restriction layers are stored and served in **EPSG:4326** (lon/lat), independent of the terrain pipeline's projected CRS.
- Each language's `highlight` string MUST be a verbatim substring of that language's `tooltip` (the frontend locates it with `indexOf` in `appendDescText`).
- i18n base language is **English**: server (`LAYERS`) text is English; `restrictionStrings.ts` provides `es` + `ca` overrides only; `en` falls back to the server text.
- Layer geometry is simplified with the existing `SIMPLIFY_TOL_DEG = 0.0001`.
- Strict mypy is enforced (`uv run mypy` must pass).

### Discovered data facts (from Task 1 — treat as verified, do not re-derive)

- **Two files per source**, each in a different CRS — the transform must read **all** matching files and reproject each to 4326 before concatenating:
  | file (in `data/restrictions/raw/`) | source | CRS |
  |---|---|---|
  | `PS.Natura2000_p_2025.gml` (peninsula+baleares) | rn2000 | EPSG:3040 |
  | `PS.Natura2000_c_2025.gml` (canarias) | rn2000 | EPSG:3040 |
  | `Enp2025_p.json` (peninsula+baleares) | enp | EPSG:25830 |
  | `Enp2025_c.json` (canarias) | enp | EPSG:32628 |
- **RN2000 ZEPA/ZEC designation is NOT a GeoPandas column.** It lives in `ps:siteDesignation/ps:DesignationType/ps:designation/@xlink:href` (INSPIRE Protected Sites schema); GDAL returns those attributes as `None`. It must be recovered by parsing the raw GML XML and joined to the geometries on the `localId` field (which GeoPandas *does* read). A feature can carry several designation codes at once (ZEPA + ZEC + LIC).
- **Designation code value sets** (last path segment of the href), including MITECO's genuine source typo which is *more common* than the correct spelling — omitting it drops ~59% of ZEPA sites:
  - `ZEPA_VALUES = {"SpecialProtectionArea", "SpecialProtecionArea"}`  ← second entry is the typo (missing "t"), intentional
  - `ZEC_VALUES = {"SpecialAreaOfConservation", "SiteOfCommunityImportance"}`
- **Name fields:** RN2000 site name = column `text`; ENP site name = column `SITE_NAME`.
- **XML namespaces** for the designation parse:
  ```python
  {"ps": "http://inspire.ec.europa.eu/schemas/ps/5.0",
   "base": "http://inspire.ec.europa.eu/schemas/base/4.0",
   "xlink": "http://www.w3.org/1999/xlink"}
  ```
  Per `ps:ProtectedSite`: localId at `ps:inspireId/base:Identifier/base:localId`; designation hrefs at `.//ps:siteDesignation/ps:DesignationType/ps:designation` read from `.attrib["{http://www.w3.org/1999/xlink}href"].rsplit("/", 1)[-1]`.
- Reading/parsing the 451 MB peninsula GML is slow-ish but fine; use `ET.iterparse` (streaming) with `elem.clear()`, never a full-DOM `ET.parse`.
- Attribution: MITECO must be credited as data author/owner somewhere user-visible.

---

### Task 1 — COMPLETE (commit `475a163`)

Download recipe + raw-file schema discovery. Done: `justfile` `fetch-restrictions` recipe downloads the two zips into `data/restrictions/raw/` idempotently; `scripts/inspect_restrictions_raw.py` inspector added; all schema facts recorded (see the "Discovered data facts" section above and `.superpowers/sdd/task-1-report.md`). `data/` is already git-ignored. Do not redo.

---

### Task 2: Multi-file loader — read all raw files, reproject each to 4326, concatenate

**Files:**
- Modify: `highliner/repositories/restrictions.py`
- Test: `tests/test_restrictions.py` (create)

**Interfaces:**
- Consumes: raw files under `data/restrictions/raw/` (Task 1).
- Produces:
  - `RAW_DIR: Path` = `Path(config.DATA_DIR) / "restrictions" / "raw"`.
  - `SOURCE_GLOBS: dict[str, tuple[str, ...]]` = `{"rn2000": ("*.gml",), "enp": ("*.geojson", "*.json")}`.
  - `_load_files(raw_dir: Path, patterns: tuple[str, ...]) -> gpd.GeoDataFrame` — read every file matching any pattern (sorted), reproject each to EPSG:4326, concatenate into one GeoDataFrame (crs 4326). Raises `FileNotFoundError` if nothing matches.

- [ ] **Step 1: Write the failing test**

Create `tests/test_restrictions.py`:

```python
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from highliner.repositories import restrictions as R

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def _write(path: Path, epsg: int, name: str) -> None:
    gpd.GeoDataFrame(
        {"SITE_NAME": [name]}, geometry=[_SQUARE], crs="EPSG:4326"
    ).to_crs(epsg).to_file(path, driver="GeoJSON")


def test_load_files_concats_and_reprojects(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _write(raw / "enp_p.json", 25830, "Peninsula")
    _write(raw / "enp_c.json", 32628, "Canarias")

    gdf = R._load_files(raw, ("*.geojson", "*.json"))

    assert gdf.crs.to_epsg() == 4326
    assert sorted(gdf["SITE_NAME"]) == ["Canarias", "Peninsula"]


def test_load_files_missing_raises(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    with pytest.raises(FileNotFoundError):
        R._load_files(raw, ("*.gml",))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_restrictions.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_load_files'`.

- [ ] **Step 3: Implement `_load_files` and the module constants**

In `highliner/repositories/restrictions.py`: remove the WFS constants (`WFS`, `_NS`, `_PAGE`, `_HEADERS`) and the `_fetch_source` function; add `import pandas as pd` (and keep `from pathlib import Path`). Add near the top, after imports:

```python
RAW_DIR = Path(config.DATA_DIR) / "restrictions" / "raw"
SOURCE_GLOBS: dict[str, tuple[str, ...]] = {
    "rn2000": ("*.gml",),
    "enp": ("*.geojson", "*.json"),
}


def _load_files(raw_dir: Path, patterns: tuple[str, ...]) -> gpd.GeoDataFrame:
    """Read every raw file matching any of ``patterns`` under ``raw_dir``,
    reproject each to EPSG:4326, and concatenate. The national datasets ship as
    a peninsula+baleares file and a canarias file, each in its own CRS."""
    frames: list[gpd.GeoDataFrame] = []
    for pattern in patterns:
        for path in sorted(raw_dir.glob(pattern)):
            gdf = gpd.read_file(path)
            if gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")
            elif gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs("EPSG:4326")
            frames.append(gdf)
    if not frames:
        raise FileNotFoundError(
            f"no raw files matching {patterns} in {raw_dir} "
            f"(run `just fetch-restrictions`)")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
```

If `import requests` is now unused in the module, remove it (check `rg -n "requests" highliner/repositories/restrictions.py`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_restrictions.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add highliner/repositories/restrictions.py tests/test_restrictions.py
git commit -m "feat: multi-file restriction loader (reproject each to 4326, concat)"
```

---

### Task 3: RN2000 designation parser + `_load_source` dispatch

**Files:**
- Modify: `highliner/repositories/restrictions.py`
- Test: `tests/test_restrictions.py`

**Interfaces:**
- Consumes: `_load_files`, `SOURCE_GLOBS`, `RAW_DIR` (Task 2).
- Produces:
  - `_parse_designations(path: Path) -> dict[str, set[str]]` — map each ProtectedSite `localId` to its set of INSPIRE designation codes, by streaming the raw GML XML.
  - `_load_source(source_key: str, raw_dir: Path | None = None) -> gpd.GeoDataFrame` — load a source's files (4326, concatenated); for `"rn2000"`, additionally attach a `designations` column (a `set[str]` per row) joined on `localId`. Raises `KeyError` for an unknown source.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_restrictions.py`:

```python
_GML = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection
    xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns:gml="http://www.opengis.net/gml/3.2"
    xmlns:ps="http://inspire.ec.europa.eu/schemas/ps/5.0"
    xmlns:base="http://inspire.ec.europa.eu/schemas/base/4.0"
    xmlns:xlink="http://www.w3.org/1999/xlink">
  <wfs:member>
    <ps:ProtectedSite>
      <ps:inspireId><base:Identifier><base:localId>ES0000197</base:localId></base:Identifier></ps:inspireId>
      <ps:siteDesignation><ps:DesignationType>
        <ps:designation xlink:href="http://inspire.ec.europa.eu/codelist/Natura2000DesignationValue/SpecialProtecionArea"/>
      </ps:DesignationType></ps:siteDesignation>
    </ps:ProtectedSite>
  </wfs:member>
  <wfs:member>
    <ps:ProtectedSite>
      <ps:inspireId><base:Identifier><base:localId>ES6300001</base:localId></base:Identifier></ps:inspireId>
      <ps:siteDesignation><ps:DesignationType>
        <ps:designation xlink:href="http://inspire.ec.europa.eu/codelist/Natura2000DesignationValue/SiteOfCommunityImportance"/>
      </ps:DesignationType></ps:siteDesignation>
      <ps:siteDesignation><ps:DesignationType>
        <ps:designation xlink:href="http://inspire.ec.europa.eu/codelist/Natura2000DesignationValue/SpecialProtectionArea"/>
      </ps:DesignationType></ps:siteDesignation>
    </ps:ProtectedSite>
  </wfs:member>
</wfs:FeatureCollection>
"""


def test_parse_designations(tmp_path: Path) -> None:
    gml = tmp_path / "rn.gml"
    gml.write_text(_GML)

    codes = R._parse_designations(gml)

    assert codes["ES0000197"] == {"SpecialProtecionArea"}          # typo-only ZEPA
    assert codes["ES6300001"] == {"SiteOfCommunityImportance", "SpecialProtectionArea"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_restrictions.py::test_parse_designations -v`
Expected: FAIL — `AttributeError: ... '_parse_designations'`.

- [ ] **Step 3: Implement the parser and `_load_source`**

Add to `highliner/repositories/restrictions.py`:

```python
import xml.etree.ElementTree as ET

_PS = "http://inspire.ec.europa.eu/schemas/ps/5.0"
_BASE = "http://inspire.ec.europa.eu/schemas/base/4.0"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_XML_NS = {"ps": _PS, "base": _BASE}


def _parse_designations(path: Path) -> dict[str, set[str]]:
    """Map each ProtectedSite localId to its INSPIRE designation codes.

    The ZEPA/ZEC designation lives in ``ps:designation``'s ``xlink:href``
    attribute, which GDAL exposes as ``None``, so stream the raw XML instead."""
    out: dict[str, set[str]] = {}
    site_tag = f"{{{_PS}}}ProtectedSite"
    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag != site_tag:
            continue
        lid_el = elem.find("ps:inspireId/base:Identifier/base:localId", _XML_NS)
        if lid_el is not None and lid_el.text:
            codes = {
                d.attrib[_XLINK_HREF].rsplit("/", 1)[-1]
                for d in elem.findall(
                    ".//ps:siteDesignation/ps:DesignationType/ps:designation", _XML_NS)
                if _XLINK_HREF in d.attrib and d.attrib[_XLINK_HREF]
            }
            out[lid_el.text] = codes
        elem.clear()
    return out


def _load_source(source_key: str,
                 raw_dir: Path | None = None) -> gpd.GeoDataFrame:
    """Load a source's raw files (EPSG:4326, concatenated). For ``rn2000`` also
    attach a ``designations`` column (set of INSPIRE codes) joined on localId."""
    base = raw_dir if raw_dir is not None else RAW_DIR
    if source_key not in SOURCE_GLOBS:
        raise KeyError(source_key)
    gdf = _load_files(base, SOURCE_GLOBS[source_key])
    if source_key == "rn2000":
        codes: dict[str, set[str]] = {}
        for path in sorted(base.glob("*.gml")):
            codes.update(_parse_designations(path))
        gdf["designations"] = [codes.get(lid, set()) for lid in gdf["localId"]]
    return gdf
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_restrictions.py -v`
Expected: PASS (all tests so far).

- [ ] **Step 5: Typecheck**

Run: `uv run mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add highliner/repositories/restrictions.py tests/test_restrictions.py
git commit -m "feat: parse RN2000 INSPIRE designations from GML, attach to source"
```

---

### Task 4: `LAYERS` registry + `build_layer` for the three national layers

**Files:**
- Modify: `highliner/repositories/restrictions.py`
- Test: `tests/test_restrictions.py`

**Interfaces:**
- Consumes: `_load_source` (Task 3), the designation value sets, the name fields.
- Produces:
  - `LAYERS: dict[str, LayerSpec]` keyed `"zepa"`, `"zec"`, `"enp"`, each `label`, `color`, `source` (key into `SOURCE_GLOBS`), `name_field`, `keep: Callable[[Mapping[str, Any]], bool]`, `tooltip`, `highlight` (English).
  - `build_layer(layer_id: str, source_cache: dict[str, gpd.GeoDataFrame]) -> gpd.GeoDataFrame` — filter the source by `keep`, normalize `name` from `name_field`, simplify, return a 4326 GeoDataFrame with columns `["name", "geometry"]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_restrictions.py`:

```python
def _rn2000_source() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "text": ["Birds Only", "Habitat Only", "Both"],
            "designations": [
                {"SpecialProtecionArea"},                       # typo ZEPA
                {"SiteOfCommunityImportance"},                  # ZEC
                {"SpecialProtectionArea", "SpecialAreaOfConservation"},
            ],
        },
        geometry=[_SQUARE, _SQUARE, _SQUARE],
        crs="EPSG:4326",
    )


def test_build_zepa_keeps_spa_incl_typo_and_both() -> None:
    gdf = R.build_layer("zepa", {"rn2000": _rn2000_source()})
    assert sorted(gdf["name"]) == ["Birds Only", "Both"]
    assert gdf.crs.to_epsg() == 4326


def test_build_zec_keeps_sci_sac_and_both() -> None:
    gdf = R.build_layer("zec", {"rn2000": _rn2000_source()})
    assert sorted(gdf["name"]) == ["Both", "Habitat Only"]


def test_build_enp_keeps_all_and_normalizes_name() -> None:
    src = gpd.GeoDataFrame(
        {"SITE_NAME": ["  Park  ", None]},
        geometry=[_SQUARE, _SQUARE], crs="EPSG:4326",
    )
    gdf = R.build_layer("enp", {"enp": src})
    assert sorted(gdf["name"]) == ["", "Park"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_restrictions.py -k build -v`
Expected: FAIL — new `LAYERS`/`build_layer` shape not present.

- [ ] **Step 3: Implement the registry and `build_layer`**

Replace the old `LayerSpec`, `LAYERS`, and `build_layer` in `highliner/repositories/restrictions.py`:

```python
from collections.abc import Mapping

ZEPA_VALUES = frozenset({"SpecialProtectionArea", "SpecialProtecionArea"})
ZEC_VALUES = frozenset({"SpecialAreaOfConservation", "SiteOfCommunityImportance"})


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
        "name_field": "text",
        "keep": lambda p: bool(ZEPA_VALUES & set(p.get("designations") or ())),
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
        "name_field": "text",
        "keep": lambda p: bool(ZEC_VALUES & set(p.get("designations") or ())),
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
        "name_field": "SITE_NAME",
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
    sub = src[src.apply(lambda row: keep(row), axis=1)]
    names = (sub[spec["name_field"]].fillna("").astype(str).str.strip().tolist()
             if len(sub) else [])
    gdf = gpd.GeoDataFrame({"name": names}, geometry=list(sub.geometry),
                           crs="EPSG:4326")
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_TOL_DEG,
                                            preserve_topology=True)
    return gdf
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_restrictions.py -v`
Expected: PASS (all restriction tests).

- [ ] **Step 5: Typecheck**

Run: `uv run mypy`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add highliner/repositories/restrictions.py tests/test_restrictions.py
git commit -m "feat: national zepa/zec/enp layer registry + build_layer"
```

---

### Task 5: Wire `fetch_all`, the CLI message, and the API registry test

**Files:**
- Modify: `highliner/repositories/restrictions.py` (`fetch_all` docstring/print only)
- Modify: `highliner/cli.py:60-63` (`_cmd_fetch_restrictions` message)
- Modify: `tests/test_api.py:161-218` (restriction tests → new ids)

**Interfaces:**
- Consumes: `LAYERS`, `build_layer` (Task 4).
- Produces: `data/restrictions/{zepa,zec,enp}.parquet` when run end-to-end.

- [ ] **Step 1: Update the API test to the new ids**

In `tests/test_api.py`, change the registry assertion in `test_restriction_layers_registry` from:
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

- [ ] **Step 2: Run the API tests**

Run: `uv run pytest tests/test_api.py -k restriction -v`
Expected: the registry test passes if Task 4 is merged (registry already serves new ids); the `_write_restriction_layer` tests pass with the renamed id. If any fail on a stale id, fix that literal. (These tests write parquet directly and do not touch raw MITECO files.)

- [ ] **Step 3: Update `fetch_all` message and CLI text**

In `highliner/repositories/restrictions.py`, update the `fetch_all` docstring to say it builds layers from the local national files under `data/restrictions/raw/` (not a WFS). In `highliner/cli.py:62`, change:
```python
    print("Downloading protected-area layers from the Generalitat WFS...")
```
to:
```python
    print("Building national protected-area layers from data/restrictions/raw/ ...")
```

- [ ] **Step 4: Full end-to-end build (integration check)**

Run: `just fetch-restrictions`
Expected: skips the download (raw files already present from Task 1), then prints one line per layer (`zepa`, `zec`, `enp`) with a feature count and KiB size, writing `data/restrictions/{zepa,zec,enp}.parquet`. Sanity: `zepa` ≈ 650 features, `zec` ≈ 2900, `enp` ≈ 1785 (order-of-magnitude; all three non-empty, no `pein`/`parcs`/`fauna` files produced). If counts are wildly off (e.g. `zepa` empty), stop — the designation join or value sets are wrong.

- [ ] **Step 5: Delete the throwaway inspector and commit**

```bash
rm scripts/inspect_restrictions_raw.py
git add highliner/repositories/restrictions.py highliner/cli.py tests/test_api.py scripts/inspect_restrictions_raw.py
git commit -m "feat: wire national restriction build end-to-end; update CLI + api tests"
```

---

### Task 6: Frontend i18n — English base, es/ca overrides for new ids

**Files:**
- Modify: `frontend/src/lib/i18n/restrictionStrings.ts`
- Modify: `frontend/src/lib/i18n/i18n.test.tsx`
- Modify: `frontend/src/components/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `restrictionText(id, lang, fallback)` (unchanged resolver).
- Produces: `RESTRICTION_STRINGS` with top-level keys `es` and `ca` (no `en`), each holding `zepa`/`zec`/`enp` entries of `{ label, tooltip, highlight }`.

- [ ] **Step 1: Rewrite `restrictionStrings.ts`**

Replace the `RESTRICTION_STRINGS` object body (keep the `import`, the `RestrictionText` interface, and the `restrictionText` resolver unchanged) with:

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

At `frontend/src/lib/i18n/i18n.test.tsx:53-95` the tests use old ids (`pein`, `fauna`, `n`) and Catalan-base semantics. Update:
- Leave the substring-invariant loop that iterates `RESTRICTION_STRINGS` (it is id-agnostic; now covers `es`/`ca`).
- Change the base-language fallback case so **`en`** returns the fallback (English is the server base now):
```typescript
  it("falls back to the server text for the base language (en)", () => {
    const fallback = { label: "L", tooltip: "T", highlight: "T" };
    expect(restrictionText("zepa", "en", fallback)).toEqual(fallback);
  });
```
- Replace the representative-text assertions with a `zepa`/`enp` override in `es`/`ca`, asserting the exact strings from Step 1, e.g.:
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

In `frontend/src/components/map/MapView.test.tsx`, the restriction fixtures use `id: "pein"` / `layer: "pein"` / `enabledRestrictions: ["pein"]` and `label: "PEIN"`. Change those literals to `"zepa"` and the label to `"ZEPA (Birds)"`. These are opaque fixtures; component logic is unaffected.

- [ ] **Step 4: Run the frontend tests**

Run: `cd frontend && npm test`
Expected: PASS. In particular the substring-invariant test passes (every `es`/`ca` `highlight` is a substring of its `tooltip`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/i18n/restrictionStrings.ts frontend/src/lib/i18n/i18n.test.tsx frontend/src/components/map/MapView.test.tsx
git commit -m "feat: national restriction i18n (English base, es/ca overrides)"
```

---

### Task 7: MITECO attribution credit

**Files:**
- Modify: `frontend/src/lib/i18n/strings.ts` (add a credit string key)
- Modify: `frontend/src/components/RestrictionLayerControls.tsx` (render the credit)
- Test: `frontend/src/components/RestrictionLayerControls.test.tsx` (create, or extend an existing controls test)

**Interfaces:**
- Consumes: the existing `STRINGS`/`useI18n()` machinery.
- Produces: a visible "Protected-area data © MITECO" line in the restriction layer controls.

- [ ] **Step 1: Read the component + strings shape first**

Read `frontend/src/components/RestrictionLayerControls.tsx` and `frontend/src/lib/i18n/strings.ts` to learn the component's props, how it reads translations (e.g. `useI18n()`), and the per-language `STRINGS` object shape. Match those patterns exactly in the steps below.

- [ ] **Step 2: Add the credit string**

In `frontend/src/lib/i18n/strings.ts`, add a `restrictionCredit` key to each language's entry:
- en: `"Protected-area data © MITECO"`
- es: `"Datos de espacios protegidos © MITECO"`
- ca: `"Dades d'espais protegits © MITECO"`

- [ ] **Step 3: Write the failing test**

Create `frontend/src/components/RestrictionLayerControls.test.tsx` (mirror the render/props setup of an existing sibling component test), asserting the credit renders:
```typescript
it("shows the MITECO data attribution", () => {
  // render with the same required props a sibling test uses
  expect(screen.getByText(/© MITECO/)).toBeInTheDocument();
});
```

- [ ] **Step 4: Run to verify it fails**

Run: `cd frontend && npm test -- RestrictionLayerControls`
Expected: FAIL — credit not rendered.

- [ ] **Step 5: Render the credit**

In `frontend/src/components/RestrictionLayerControls.tsx`, after the list of layer toggles, add a small muted line using the component's existing i18n accessor, e.g.:
```tsx
<p className="text-xs text-muted-foreground mt-2">{t.restrictionCredit}</p>
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd frontend && npm test -- RestrictionLayerControls`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/i18n/strings.ts frontend/src/components/RestrictionLayerControls.tsx frontend/src/components/RestrictionLayerControls.test.tsx
git commit -m "feat: MITECO attribution credit in restriction panel"
```

---

### Task 8: Full verification + docs

**Files:**
- Modify: `AGENTS.md` (restrictions section)
- Modify: `NEW_LOCATIONS.md` (layer-list reference)

- [ ] **Step 1: Backend suite** — Run: `uv run pytest` — Expected: all pass.
- [ ] **Step 2: Typecheck** — Run: `uv run mypy` — Expected: no errors.
- [ ] **Step 3: Frontend suite** — Run: `cd frontend && npm test` — Expected: all pass.
- [ ] **Step 4: Manual smoke** — `just dev` + `just dev-web`, open the map over a non-Catalan cliff (Riglos ~ `-0.53, 42.34`, El Chorro ~ `-4.77, 36.90`); toggle `ZEPA (Birds)` / `ZEC / LIC` / `Protected Natural Areas`; confirm polygons render and popups show the site name + English tooltip; switch UI language to es/ca and confirm the tooltip and the credit line change.
- [ ] **Step 5: Update docs** — In `AGENTS.md`, update the restrictions description: source is MITECO's Banco de Datos de la Naturaleza national files (RN2000 GML + ENP GeoJSON, peninsula + canarias) downloaded by `just fetch-restrictions`, layers `zepa`/`zec`/`enp`, RN2000 designation parsed from GML XML, English-base i18n. In `NEW_LOCATIONS.md`, replace the `zec/zepa/pein/parcs/fauna` example split reference with the current `zepa/zec/enp` national layers.
- [ ] **Step 6: Commit** — `git add AGENTS.md NEW_LOCATIONS.md && git commit -m "docs: national MITECO restrictions in AGENTS.md and NEW_LOCATIONS.md"`

---

## Notes for the implementer

- `zepa` and `zec` share the `rn2000` source; `build_layer`'s `source_cache` reads (and XML-parses) it once across both — do not load it twice.
- The `SpecialProtecionArea` typo in `ZEPA_VALUES` is deliberate — it is MITECO's misspelling and is more common than the correct spelling. Do not "fix" it.
- Never full-DOM-parse the 451 MB GML; `_parse_designations` uses `ET.iterparse` + `elem.clear()`.
- The two ENP files are in different CRSes (25830 vs 32628); `_load_files` reprojects each independently before concatenating — do not assume one CRS.
