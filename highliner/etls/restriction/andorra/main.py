"""Andorra natural-park overlay adapter."""
import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "andorra"
__all__ = ["main", "shutil", "subprocess"]
SOURCE_URL = ("https://www.iea.ad/images/stories/Sigma/Mapes_E00/"
              "Parcs_Naturals_ArcGis.rar")
SOURCE_FILE: Final[str] = "Parcs_Naturals_ArcGis.rar"
SPECS = {"ad_natural_parks": shared.LayerBuildSpec(
    "ad_natural_parks", "natural_parks", "NOM", lambda _props: True)}


def _download(url: str, destination: Path) -> None:
    with requests.get(url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with destination.open("wb") as output:
            for block in response.iter_content(1024 * 1024):
                if block:
                    output.write(block)


def download_source(raw_dir: Path) -> None:
    """Cache the official ArcGIS export from Andorra's environment institute."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    archive = raw_dir / SOURCE_FILE
    if not archive.exists():
        _download(SOURCE_URL, archive)
    if not list(raw_dir.glob("*.shp")):
        unar = shutil.which("unar")
        if unar is None:
            raise RuntimeError("Andorra restrictions require the `unar` command")
        subprocess.run([unar, "-quiet", "-o", str(raw_dir), str(archive)],
                       check=True)


def _load_source(raw_dir: Path) -> gpd.GeoDataFrame:
    paths = sorted(raw_dir.glob("*.shp"))
    if not paths:
        raise FileNotFoundError(f"no natural-park shapefile in {raw_dir}")
    source = gpd.read_file(paths[0])
    if source.crs is None:
        raise ValueError(f"{paths[0]} has no CRS")
    return source.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-restrictions-andorra")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_source(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda _source: _load_source(raw_dir), restrictions_dir)
