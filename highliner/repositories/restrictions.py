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
from functools import lru_cache
from typing import Any, Callable, TypedDict
import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

from highliner.core import config


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


class LayerSpec(TypedDict):
    label: str
    color: str
    source: str
    name_field: str
    keep: Callable[[dict[str, Any]], bool]
    tooltip: str
    highlight: str

# Douglas-Peucker tolerance in degrees (~11 m). Source geometry is digitized at
# 1:5,000-1:50,000, far finer than the web map renders; simplifying here cuts
# stored size to ~15% of raw with no visible change at map zoom.
SIMPLIFY_TOL_DEG = 0.0001

# Derived overlay layers. Each pulls from a source feature type, optionally
# filters by a predicate on properties, and renames one field to `name`.
# Note: PEIN legally incorporates all Xarxa Natura 2000 (ZEC/ZEPA) spaces, so
# those layers would just overlap PEIN on the map and are intentionally omitted.
LAYERS: dict[str, LayerSpec] = {
    "pein": {
        "label": "PEIN",
        "color": "#ff7f00",
        "source": "PEIN",
        "name_field": "NOM_PEIN",
        "keep": lambda p: True,
        "tooltip": ("Pla d'Espais d'Interès Natural - el nivell bàsic de "
                    "protecció a Catalunya (Decret 328/1992); inclou els espais "
                    "de la Xarxa Natura 2000. Règim urbanístic rigorós; les "
                    "activitats que puguin lesionar els valors naturals poden "
                    "requerir avaluació d'impacte ambiental. Molts cingles "
                    "tenen tancaments estacionals d'escalada per la nidificació "
                    "de rapinyaires (aprox. gener-agost, varia segons l'espai)."),
        # substring of `tooltip` to emphasize (the highliner-relevant part)
        "highlight": ("les activitats que puguin lesionar els valors naturals "
                      "poden requerir avaluació d'impacte ambiental. Molts "
                      "cingles tenen tancaments estacionals d'escalada per la "
                      "nidificació de rapinyaires (aprox. gener-agost, varia "
                      "segons l'espai)."),
    },
    "parcs": {
        "label": "Parcs Naturals",
        "color": "#6a3d9a",
        "source": "PARCSNATURALS",
        "name_field": "NOM_ESPAI",
        "keep": lambda p: True,
        "tooltip": ("Nivell de protecció més alt (ENPE), cadascun amb el seu "
                    "pla de gestió. Activitats com l'escalada, el vivac, els "
                    "drons i els actes organitzats estan regulades i sovint "
                    "necessiten autorització de l'òrgan gestor del parc."),
        "highlight": ("Activitats com l'escalada, el vivac, els drons i els "
                      "actes organitzats estan regulades i sovint necessiten "
                      "autorització de l'òrgan gestor del parc."),
    },
    "fauna": {
        "label": "Reserves de Fauna",
        "color": "#e31a1c",
        "source": "ENPE",
        "name_field": "NOM_RNFS",
        "keep": lambda p: bool((p.get("NOM_RNFS") or "").strip()),
        "tooltip": ("Reserva Natural de Fauna Salvatge - protegeix la fauna. "
                    "Es prohibeix qualsevol activitat que pugui perjudicar "
                    "directament o indirectament la fauna protegida; consulteu "
                    "l'òrgan gestor abans de fer cap activitat."),
        "highlight": ("Es prohibeix qualsevol activitat que pugui perjudicar "
                      "directament o indirectament la fauna protegida; "
                      "consulteu l'òrgan gestor abans de fer cap activitat."),
    },
}


def build_layer(layer_id: str,
                source_cache: dict[str, list[dict[str, Any]]]) -> gpd.GeoDataFrame:
    """Filter/normalize/simplify a source feature type into a derived layer."""
    spec = LAYERS[layer_id]
    src = source_cache.get(spec["source"])
    if src is None:
        src = source_cache[spec["source"]] = _fetch_source(spec["source"])
    names, geoms = [], []
    for f in src:
        props = f.get("properties", {})
        if not spec["keep"](props):
            continue
        names.append((props.get(spec["name_field"]) or "").strip())
        geoms.append(shape(f["geometry"]))
    gdf = gpd.GeoDataFrame({"name": names}, geometry=geoms, crs="EPSG:4326")
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_TOL_DEG,
                                            preserve_topology=True)
    return gdf


def fetch_all(dest_dir: Path | None = None) -> dict[str, Path]:
    """Download every layer and write data/restrictions/<id>.parquet."""
    dest_dir = Path(dest_dir or (config.DATA_DIR / "restrictions"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    source_cache: dict[str, list[dict[str, Any]]] = {}
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
