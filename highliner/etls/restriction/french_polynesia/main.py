"""PatriNat protected-area overlays for French Polynesia.

French Polynesia is outside Natura 2000.  The national PatriNat WFS instead
publishes the Ramsar and UNESCO biosphere designations that cover its protected
islands and lagoons; both can affect access and disturbance-sensitive rigging.
"""
import argparse
import json
from pathlib import Path
from typing import Any, Final, cast

import geopandas as gpd
import pandas as pd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "french_polynesia"
WFS_URL = "https://data.geopf.fr/wfs/ows"
_PAGE_SIZE = 1000
_TYPES = ("patrinat_ramsar:ramsar", "patrinat_bios:bios")
SPECS = {"pf_protected": shared.LayerBuildSpec(
    "pf_protected", "protected", "nom_site", lambda _props: True)}


def _fetch_page(type_name: str, start: int) -> dict[str, Any]:
    response = requests.get(WFS_URL, params={
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": type_name, "SRSNAME": "urn:ogc:def:crs:EPSG::4326",
        "outputFormat": "application/json", "COUNT": str(_PAGE_SIZE),
        "STARTINDEX": str(start),
    }, timeout=300)
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def _download_type(type_name: str) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    start = 0
    while True:
        page = _fetch_page(type_name, start)
        batch = page.get("features", [])
        features.extend(batch)
        if len(batch) < _PAGE_SIZE:
            return features
        start += len(batch)


def download_sources(raw_dir: Path) -> None:
    """Cache the protected-area catalogue as one portable GeoJSON file."""
    path = raw_dir / "protected.geojson"
    if path.exists():
        return
    raw_dir.mkdir(parents=True, exist_ok=True)
    features = [feature for type_name in _TYPES
                for feature in _download_type(type_name)]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source != "protected":
        raise KeyError(source)
    frame = gpd.read_file(raw_dir / "protected.geojson")
    if frame.crs is None:
        frame = frame.set_crs("EPSG:4326")
    elif frame.crs.to_epsg() != 4326:
        frame = frame.to_crs("EPSG:4326")
    territory = frame.get("territoire", pd.Series("", index=frame.index))
    return frame[territory.eq("PYF")]


def main(argv: list[str] | None = None) -> None:
    """Download and write French Polynesia's protected-area overlay."""
    parser = argparse.ArgumentParser(prog="highliner-restrictions-french-polynesia")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir), restrictions_dir)


if __name__ == "__main__":
    main()
