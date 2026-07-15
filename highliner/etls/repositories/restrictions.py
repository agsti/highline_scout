"""Build protected-area overlay layers for all of Spain and store them locally.

Source: MITECO's (national) Banco de Datos de la Naturaleza files, placed
under ``data/spain/restrictions/raw/`` by ``just fetch-restrictions``:

    rn2000  Red Natura 2000 GML (INSPIRE ProtectedSites), drives ``zepa`` and
            ``zec`` by filtering on RN2000 designation
    enp     Espacios Naturales Protegidos GeoJSON, drives ``enp``

Each source ships as two files - one covering the peninsula + Baleares, one
covering Canarias - in different CRSes; ``_load_files`` reprojects each to
EPSG:4326 independently before concatenating. The RN2000 GML doesn't expose
the ZEPA/ZEC designation through GDAL's normal attribute reader, so
``_parse_designations`` streams the raw XML (``ps:designation``'s
``xlink:href``) and joins the result onto the GeoDataFrame by ``localId``.

We derive three overlay layers relevant to highline access:

    zepa  Special Protection Area for Birds  (rn2000, ZEPA designation)
    zec   Site/Area of Community Importance  (rn2000, ZEC/LIC designation)
    enp   Protected Natural Area             (enp, all features)

Each derived layer is simplified (geometry detail is far finer than map scale
needs) and written to ``data/spain/restrictions/<id>.parquet`` with only a
normalized ``name`` property.

This module owns the build side: transforming the layers from the raw files
(``fetch_all``). The ``LAYERS`` registry that drives the build lives in the
shared ``highliner.core.restrictions`` (the serving side reads it too), and
reading stored layers (``load_layer``) lives in
``highliner.server.repositories.restrictions``.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

import geopandas as gpd
import pandas as pd

from highliner.core import config
from highliner.core.restrictions import LAYERS

# The MITECO overlays cover Spain, so they live under that country's data dir.
RESTRICTIONS_COUNTRY = "spain"
RESTRICTIONS_DIR = Path(config.DATA_DIR) / RESTRICTIONS_COUNTRY / "restrictions"
RAW_DIR = RESTRICTIONS_DIR / "raw"
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
        # GDAL does not expose the INSPIRE designation (it lives in a
        # ps:designation xlink:href attribute), so the same GML files are read a
        # second time via raw XML to recover the ZEPA/ZEC codes, joined on
        # localId below. Use SOURCE_GLOBS so this stays in sync with the
        # geometry load in _load_files above.
        codes: dict[str, set[str]] = {}
        for pattern in SOURCE_GLOBS["rn2000"]:
            for path in sorted(base.glob(pattern)):
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
                if path.suffix.lower() in (".geojson", ".json"):
                    gdf = gdf.set_crs("EPSG:4326")  # GeoJSON is WGS84 by spec
                else:
                    raise ValueError(
                        f"{path}: source has no CRS and is not GeoJSON; "
                        f"refusing to assume EPSG:4326")
            elif gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs("EPSG:4326")
            frames.append(gdf)
    if not frames:
        raise FileNotFoundError(
            f"no raw files matching {patterns} in {raw_dir} "
            f"(run `just fetch-restrictions`)")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


# Douglas-Peucker tolerance in degrees (~11 m). Source geometry is digitized at
# 1:5,000-1:50,000, far finer than the web map renders; simplifying here cuts
# stored size to ~15% of raw with no visible change at map zoom.
SIMPLIFY_TOL_DEG = 0.0001


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


def fetch_all(dest_dir: Path | None = None,
              raw_dir: Path | None = None) -> dict[str, Path]:
    """Build every layer from the local national files under ``raw_dir``
    (default ``data/spain/restrictions/raw/``) and write
    ``data/spain/restrictions/<id>.parquet``."""
    dest_dir = Path(dest_dir or RESTRICTIONS_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    source_cache: dict[str, gpd.GeoDataFrame] = {}
    written: dict[str, Path] = {}
    for layer_id in LAYERS:
        src_key = LAYERS[layer_id]["source"]
        if src_key not in source_cache:
            source_cache[src_key] = _load_source(src_key, raw_dir)
        gdf = build_layer(layer_id, source_cache)
        path = dest_dir / f"{layer_id}.parquet"
        gdf.to_parquet(path)
        written[layer_id] = path
        print(f"  {layer_id:6s} {len(gdf):4d} features  "
              f"{path.stat().st_size / 1024:8.1f} KiB  -> {path}")
    return written
