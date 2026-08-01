"""Build Canada's national CPCAD protected/conserved-area overlay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "canada"
QUERY_URL: Final[str] = ("https://maps-cartes.ec.gc.ca/arcgis/rest/services/"
                         "CWS_SCF/CPCAD/MapServer/0/query")
SPECS = (shared.LayerBuildSpec("ca_protected", "cpcad", "NAME_E",
                               lambda _props: True),)


def download_sources(raw_dir: Path) -> None:
    """Download CPCAD's authoritative national protected-area GeoJSON once."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / "cpcad.geojson"
    if dest.exists():
        return
    params = {"where": "1=1", "outFields": "NAME_E", "returnGeometry": "true",
              "f": "geojson", "resultRecordCount": "25000"}
    response = requests.get(QUERY_URL, params=params, timeout=600)
    response.raise_for_status()
    body = response.json()
    dest.write_text(json.dumps(body))


def _load_source(raw_dir: Path) -> gpd.GeoDataFrame:
    source = gpd.read_file(raw_dir / "cpcad.geojson")
    if source.crs is None:
        return source.set_crs("EPSG:4326")
    return source.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-canada")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    out = args.data_dir / COUNTRY / "restrictions"
    raw = out / "raw"
    download_sources(raw)
    shared.write_layers(SPECS, lambda _source: _load_source(raw), out)
