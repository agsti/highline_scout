"""Download protected-area boundaries for Catalonia and store them locally.

Source: the Generalitat's unified "Espais Naturals" WFS, which carries every
protected-area figure as a separate feature type (or as attribute flags within
one). We derive overlay layers relevant to highline access:

    pein   PEIN                (ESPAISNATURALS_PEIN)
    parcs  Parcs Naturals      (ESPAISNATURALS_PARCSNATURALS)
    fauna  Reserves de Fauna   (ESPAISNATURALS_ENPE where NOM_RNFS is set)

The WFS serves GeoJSON in EPSG:4326 (lon/lat), which is exactly what the web
map consumes, so no reprojection is needed. Each derived layer is simplified
(geometry detail is far finer than map scale needs) and written to
``data/restrictions/<id>.parquet`` with only a normalized ``name`` property.

This module owns persistence: the WFS download/transform (``fetch_all``) and
reading stored layers (``load_layer``). The ``LAYERS`` registry of overlay
specifications lives here too, since the download is driven by it; the serving
helpers that consume it (``layer_meta``, ``clip_to_features``) live in
``highliner.services.restrictions``.
"""
from pathlib import Path
from collections.abc import Mapping
from functools import lru_cache
from typing import Any, Callable, TypedDict
import xml.etree.ElementTree as ET
import geopandas as gpd
import pandas as pd

from highliner.core import config


RAW_DIR = Path(config.DATA_DIR) / "restrictions" / "raw"
SOURCE_GLOBS: dict[str, tuple[str, ...]] = {
    "rn2000": ("*.gml",),
    "enp": ("*.geojson", "*.json"),
}

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

# Douglas-Peucker tolerance in degrees (~11 m). Source geometry is digitized at
# 1:5,000-1:50,000, far finer than the web map renders; simplifying here cuts
# stored size to ~15% of raw with no visible change at map zoom.
SIMPLIFY_TOL_DEG = 0.0001

# Derived overlay layers. Each pulls from a loaded source and optionally
# filters by a predicate on properties, and renames one field to `name`.
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
    if len(sub) == 0:
        return gpd.GeoDataFrame({"name": []}, geometry=[], crs="EPSG:4326")
    names = sub[spec["name_field"]].fillna("").astype(str).str.strip().tolist()
    gdf = gpd.GeoDataFrame({"name": names}, geometry=list(sub.geometry),
                           crs="EPSG:4326")
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_TOL_DEG,
                                            preserve_topology=True)
    return gdf


def fetch_all(dest_dir: Path | None = None) -> dict[str, Path]:
    """Download every layer and write data/restrictions/<id>.parquet."""
    dest_dir = Path(dest_dir or (config.DATA_DIR / "restrictions"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    source_cache: dict[str, gpd.GeoDataFrame] = {}
    written: dict[str, Path] = {}
    for layer_id in LAYERS:
        gdf = build_layer(layer_id, source_cache)
        path = dest_dir / f"{layer_id}.parquet"
        gdf.to_parquet(path)
        written[layer_id] = path
        print(f"  {layer_id:6s} {len(gdf):4d} features  "
              f"{path.stat().st_size / 1024:8.1f} KiB  -> {path}")
    return written


@lru_cache(maxsize=32)
def load_layer(path_str: str) -> gpd.GeoDataFrame:
    """Read a stored layer (cached for the process); layers are small."""
    return gpd.read_parquet(path_str)
