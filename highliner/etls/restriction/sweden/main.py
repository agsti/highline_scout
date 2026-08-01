"""Naturvårdsverket protected-area source adapter for Sweden."""
import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "sweden"
_NATURA_WFS: Final[str] = "https://geodata.naturvardsverket.se/n2000/wfs"
_PROTECTED_WFS: Final[str] = (
    "https://geodata.naturvardsverket.se/naturvardsregistret/wfs")
_SOURCES: dict[str, tuple[str, str]] = {
    "natura2000": (_NATURA_WFS, "N2000_WFS:N2000"),
    "protected": (_PROTECTED_WFS, "Naturvardsregistret_WFS:SkyddadeOmraden"),
}


def _has_birds(properties: Mapping[str, Any]) -> bool:
    return "SPA" in str(properties.get("OMRADESTYP") or "")


def _has_habitats(properties: Mapping[str, Any]) -> bool:
    return "SCI" in str(properties.get("OMRADESTYP") or "")


SPECS = {
    "zepa": shared.LayerBuildSpec("zepa", "natura2000", "OMRADESNAMN", _has_birds),
    "zec": shared.LayerBuildSpec("zec", "natura2000", "OMRADESNAMN", _has_habitats),
    "enp": shared.LayerBuildSpec("enp", "protected", "OMRADESNAMN",
                                  lambda properties: True),
}


def download_sources(raw_dir: Path) -> None:
    """Download the official national Swedish WFS layers as GeoJSON."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, (url, type_name) in _SOURCES.items():
        path = raw_dir / f"{source}.geojson"
        if path.exists() and path.stat().st_size:
            continue
        response = requests.get(url, params={
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": type_name, "outputFormat": "GEOJSON",
        }, timeout=300)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload.get("features"), list):
            raise RuntimeError(f"Naturvårdsverket WFS returned invalid {source} data")
        path.write_text(json.dumps(payload))


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source not in _SOURCES:
        raise KeyError(source)
    path = raw_dir / f"{source}.geojson"
    if not path.exists():
        raise FileNotFoundError(f"no {source} source in {raw_dir}")
    frame = gpd.read_file(path)
    if frame.crs is None:
        raise ValueError(f"{path}: source has no CRS")
    return frame if frame.crs.to_epsg() == 4326 else frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    """Download and transform Swedish Natura 2000 and protected-area overlays."""
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-sweden")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir),
                        restrictions_dir)
