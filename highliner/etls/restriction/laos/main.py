"""Open Development Mekong protected-area adapter for Laos."""
import argparse
import zipfile
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "laos"
URL: Final[str] = ("https://data.opendevelopmentmekong.net/lo/dataset/"
                   "2ec77628-2d75-4031-85f2-18ddac89e5ec/resource/"
                   "90cb4910-d81e-4767-9a18-060f65af1cfd/download/"
                   "protected_areas_laos.zip")
SPECS = {"la_protected_areas": shared.LayerBuildSpec(
    "la_protected_areas", "protected_areas", "name", lambda _props: True)}


def _download_sources(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    if any(raw_dir.glob("*.shp")):
        return
    archive = raw_dir / "protected_areas.zip"
    with requests.get(URL, stream=True, timeout=300) as response:
        response.raise_for_status()
        with archive.open("wb") as output:
            for block in response.iter_content(1024 * 1024):
                if block:
                    output.write(block)
    with zipfile.ZipFile(archive) as source:
        source.extractall(raw_dir)
    archive.unlink()


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source != "protected_areas":
        raise KeyError(source)
    path = next(raw_dir.rglob("*.shp"), None)
    if path is None:
        raise FileNotFoundError(f"no protected-area shapefile in {raw_dir}")
    frame = gpd.read_file(path)
    if frame.crs is None:
        frame = frame.set_crs("EPSG:4326")
    return frame if frame.crs.to_epsg() == 4326 else frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-laos")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    _download_sources(raw_dir)
    shared.write_layers(SPECS.values(), lambda source: _load_source(source, raw_dir),
                        restrictions_dir)
