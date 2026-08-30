"""ARSO protected-area adapter for Slovenia."""
import argparse
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "slovenia"
__all__ = ["main", "shared"]
_BASE = "https://gis.arso.gov.si/geoserver-beta/SI.ARSO.NATURA/wfs"
_NATURA_QUERY = ("?service=WFS&version=2.0.0&request=GetFeature&"
                 "typeNames=SI.ARSO.NATURA:NATURA_2000&"
                 "outputFormat=application/json")
SOURCE_URLS = {
    "zepa": f"{_BASE}{_NATURA_QUERY}",
    "zec": f"{_BASE}{_NATURA_QUERY}",
    "enp": "http://gis.arso.gov.si/related/atom/inspire/data/SI.ARSO.ZAV_OBM_POLI.zip",
}
SPECS = {key: shared.LayerBuildSpec(key, key, "NAME", lambda _props: True)
         for key in SOURCE_URLS}


def _download(url: str, path: Path) -> None:
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    path.write_bytes(response.content)


def download_sources(raw_dir: Path) -> None:
    """Download ARSO's national Natura 2000 and protected-area exports."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, url in SOURCE_URLS.items():
        path = raw_dir / f"{source}{'.zip' if source == 'enp' else '.geojson'}"
        if not path.exists():
            _download(url, path)


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    suffix = ".zip" if source == "enp" else ".geojson"
    frame = gpd.read_file(raw_dir / f"{source}{suffix}")
    if frame.crs is None:
        raise ValueError(f"Slovenia {source} source has no CRS")
    return frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-slovenia")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(), lambda key: _load_source(key, raw_dir),
                        restrictions_dir)
