"""Hong Kong protected areas from UNEP-WCMC's authoritative WDPCA service."""
import argparse
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "hong_kong"
SOURCE_URL: Final[str] = ("https://data-gis.unep-wcmc.org/server/rest/services/"
                          "ProtectedPlanet/WDPCA/FeatureServer/1/query")
SOURCE_FILE: Final[str] = "protected_areas.geojson"
SPECS = {"hk_country_parks": shared.LayerBuildSpec(
    "hk_country_parks", "protected_areas", "name_eng",
    lambda props: props.get("realm") != "Marine")}


def download_sources(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / SOURCE_FILE
    if dest.exists():
        return
    response = requests.get(SOURCE_URL, params={
        "where": "iso3='HKG'", "outFields": "*", "f": "geojson",
    }, timeout=300)
    response.raise_for_status()
    dest.write_bytes(response.content)


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source != "protected_areas":
        raise KeyError(source)
    path = raw_dir / SOURCE_FILE
    if not path.exists():
        raise FileNotFoundError(f"no Hong Kong protected areas in {raw_dir}")
    frame = gpd.read_file(path)
    if frame.crs is None:
        return frame.set_crs("EPSG:4326")
    return frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-restrictions-hong-kong")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir), restrictions_dir)
