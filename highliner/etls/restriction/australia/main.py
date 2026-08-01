"""CAPAD protected-area adapter for Australia."""
import argparse
import zipfile
from pathlib import Path
from typing import Final
from urllib.request import urlretrieve

import geopandas as gpd

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "australia"
SOURCE: Final[str] = "capad"
SOURCE_URL: Final[str] = ("https://www.dcceew.gov.au/sites/default/files/"
                         "documents/capad2024-terrestrial-shapefile.zip")
SPECS = {"au_capad": shared.LayerBuildSpec("au_capad", SOURCE, "NAME", lambda _: True)}


def download_sources(raw_dir: Path) -> Path:
    """Download the Commonwealth CAPAD terrestrial protected-area archive."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    existing = next(raw_dir.glob("*.shp"), None)
    if existing is not None:
        return existing
    archive = raw_dir / "capad.zip"
    urlretrieve(SOURCE_URL, archive)
    with zipfile.ZipFile(archive) as source:
        source.extractall(raw_dir)
    archive.unlink()
    path = next(raw_dir.rglob("*.shp"), None)
    if path is None:
        raise RuntimeError("CAPAD archive contains no shapefile")
    return path


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source != SOURCE:
        raise KeyError(source)
    frame = gpd.read_file(download_sources(raw_dir))
    return frame if frame.crs.to_epsg() == 4326 else frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    """Build Australia's CAPAD protected-area overlay."""
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-australia")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    directory = args.data_dir / COUNTRY / "restrictions"
    shared.write_layers(SPECS.values(), lambda source: _load_source(
        source, directory / "raw"), directory)
