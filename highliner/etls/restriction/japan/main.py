"""Japanese protected-area overlays from the MOE Biodiversity Center."""
import argparse
import zipfile
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "japan"
SOURCE_URLS = {
    "jp_national_parks": "https://www.biodic.go.jp/trialSystem/Data/SHP/nps/nps_all.zip",
    "jp_wildlife_areas": "https://www.biodic.go.jp/trialSystem/Data/SHP/nwp/nwp_all.zip",
}
SPECS = {layer: shared.LayerBuildSpec(layer, layer, "NAME", lambda _: True)
         for layer in SOURCE_URLS}


def _download(url: str, path: Path) -> None:
    with requests.get(url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with path.open("wb") as output:
            for block in response.iter_content(1024 * 1024):
                if block:
                    output.write(block)


def download_sources(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for layer, url in SOURCE_URLS.items():
        dest = raw_dir / layer
        if list(dest.rglob("*.shp")):
            continue
        archive = raw_dir / f"{layer}.zip"
        if not archive.exists():
            _download(url, archive)
        dest.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(dest)


def _load_source(layer: str, raw_dir: Path) -> gpd.GeoDataFrame:
    frame = gpd.read_file(next((raw_dir / layer).rglob("*.shp")))
    if frame.crs is None:
        return frame.set_crs("EPSG:4326")
    return frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-restrictions-japan")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    raw_dir = args.data_dir / COUNTRY / "restrictions" / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(), lambda layer: _load_source(layer, raw_dir),
                        raw_dir.parent)
