"""Belgian Natura 2000 protected-area adapter.

Belgium has no national protected-area service — the register is regional — so
two unrelated sources are stitched into one pair of overlays:

* **Flanders**, from Digitaal Vlaanderen's Mercator WFS, which publishes the
  two directives as separate layers in Lambert 72: ``ps:ps_vglrl``
  (Vogelrichtlijn / Birds) and ``ps:ps_hbtrl`` (Habitatrichtlijn / Habitats).
* **Wallonia**, from SPW's ArcGIS ``NATURA2000_SDF`` layer, which publishes one
  perimeter per site and carries **no** Birds/Habitats split. Each Wallonian
  site is therefore emitted under *both* overlays. For an informational "you
  are inside a protected area" warning that is the conservative reading — the
  site shows up whichever overlay is on — whereas assigning a directive per
  site would invent a fact the source does not carry.

Brussels is left out: it holds no terrain this pipeline would anchor on. The
two overlays reuse Spain's ``zepa``/``zec`` ids and display metadata.
"""
import argparse
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import geopandas as gpd
import pandas as pd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "belgium"
FLANDERS_WFS: Final[str] = (
    "https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/wfs")
# The Mercator WFS answers GeoJSON in the service's native Lambert 72 rather
# than the GeoJSON default of WGS84, so the CRS is asserted on read.
FLANDERS_CRS: Final[str] = "EPSG:31370"
WALLONIA_QUERY: Final[str] = (
    "https://geoservices.wallonie.be/arcgis/rest/services/FAUNE_FLORE/"
    "NATURA2000_SDF/MapServer/0/query")
WALLONIA_PAGE: Final[int] = 50
_SOURCE: Final[str] = "natura"
_ATTEMPTS: Final[int] = 4

# raw file stem -> (WFS type name, name field, designations it carries)
FLANDERS_PARTS: Final[dict[str, tuple[str, str, str]]] = {
    "flanders_spa": ("ps:ps_vglrl", "gebnaam", "SPA"),
    "flanders_sac": ("ps:ps_hbtrl", "naam", "SAC"),
}
WALLONIA_PART: Final[tuple[str, str]] = ("NOM", "SPA,SAC")


def _has_birds(props: Mapping[str, Any]) -> bool:
    """Whether a site carries a Birds Directive (SPA) designation."""
    return "SPA" in str(props.get("designation") or "")


def _has_habitats(props: Mapping[str, Any]) -> bool:
    """Whether a site carries a Habitats Directive (SAC) designation."""
    return "SAC" in str(props.get("designation") or "")


SPECS: dict[str, shared.LayerBuildSpec] = {
    "zepa": shared.LayerBuildSpec("zepa", _SOURCE, "name", _has_birds),
    "zec": shared.LayerBuildSpec("zec", _SOURCE, "name", _has_habitats),
}


def _get(url: str, params: dict[str, Any]) -> Any:
    """GET a JSON payload, retrying transient failures then giving up."""
    for attempt in range(_ATTEMPTS):
        try:
            response = requests.get(url, params=params, timeout=300)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == _ATTEMPTS - 1:
                raise
            time.sleep(2.0 ** attempt)
    raise RuntimeError("unreachable")


def _write_features(path: Path, features: list[Any], what: str) -> None:
    if not features:
        raise RuntimeError(f"{what} returned no Natura 2000 features")
    path.write_text(json.dumps({"type": "FeatureCollection",
                                "features": features}))


def _download_flanders(raw_dir: Path, key: str, type_name: str) -> None:
    """Download one Flemish directive layer once, as raw GeoJSON."""
    path = raw_dir / f"{key}.geojson"
    if path.exists() and path.stat().st_size > 0:
        return
    payload = _get(FLANDERS_WFS, {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": type_name, "outputFormat": "application/json"})
    _write_features(path, payload.get("features") or [], type_name)


def _download_wallonia(raw_dir: Path) -> None:
    """Page SPW's ArcGIS query endpoint into one raw GeoJSON file.

    The layer exceeds the server's transfer limit in one shot, and ArcGIS
    reports its own errors inside a 200 response, so both are handled here.
    """
    path = raw_dir / "wallonia.geojson"
    if path.exists() and path.stat().st_size > 0:
        return
    features: list[Any] = []
    while True:
        payload = _get(WALLONIA_QUERY, {
            "where": "1=1", "outFields": WALLONIA_PART[0], "f": "geojson",
            "outSR": "4326", "orderByFields": "OBJECTID",
            "resultOffset": len(features),
            "resultRecordCount": WALLONIA_PAGE})
        if "error" in payload:
            raise RuntimeError(f"SPW Natura 2000 query failed: "
                               f"{payload['error'].get('message')}")
        batch = payload.get("features") or []
        features.extend(batch)
        if len(batch) < WALLONIA_PAGE:
            break
    _write_features(path, features, "SPW NATURA2000_SDF")


def download_sources(raw_dir: Path) -> None:
    """Fetch every regional Natura 2000 source that is not already cached."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for key, (type_name, _name_field, _designation) in FLANDERS_PARTS.items():
        _download_flanders(raw_dir, key, type_name)
    _download_wallonia(raw_dir)


def _read_part(raw_dir: Path, key: str, name_field: str, designation: str,
               crs: str) -> gpd.GeoDataFrame:
    """Normalize one region's raw file to name + designation in WGS84."""
    frame = gpd.read_file(raw_dir / f"{key}.geojson")
    frame = frame.set_crs(crs, allow_override=True).to_crs("EPSG:4326")
    return gpd.GeoDataFrame(
        {"name": frame[name_field].fillna("").astype(str).tolist(),
         "designation": [designation] * len(frame)},
        geometry=list(frame.geometry), crs="EPSG:4326")


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source != _SOURCE:
        raise KeyError(source)
    parts = [_read_part(raw_dir, key, name_field, designation, FLANDERS_CRS)
             for key, (_type, name_field, designation)
             in FLANDERS_PARTS.items()]
    parts.append(_read_part(raw_dir, "wallonia", WALLONIA_PART[0],
                            WALLONIA_PART[1], "EPSG:4326"))
    merged = pd.concat(parts, ignore_index=True)
    return gpd.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    """Download and transform Belgium's regional Natura 2000 overlays."""
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-belgium")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir),
                        restrictions_dir)


if __name__ == "__main__":
    main()
