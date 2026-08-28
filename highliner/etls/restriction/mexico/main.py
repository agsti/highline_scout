"""CONANP federal protected natural areas adapter for Mexico."""
import argparse
import zipfile
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "mexico"
__all__ = ["main", "shared"]
SOURCE_GLOBS = {"anp": ("*.shp",)}
SOURCE_URLS = {
    "anp": ("https://sig.conanp.gob.mx/container/descargas/files/shape/"
            "232-ANP_ITRF08_19162026.zip"),
}
SPECS = {
    "mx_anp": shared.LayerBuildSpec("mx_anp", "anp", "NOMBRE", lambda _props: True),
}


def _load_source(source_key: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source_key not in SOURCE_GLOBS:
        raise KeyError(source_key)
    paths = sorted(raw_dir.glob("*.shp"))
    if not paths:
        raise FileNotFoundError(
            "no CONANP shapefile (run `just etl-restriction mexico`)")
    source = gpd.read_file(paths[0])
    if source.crs is None:
        raise ValueError(f"{paths[0]} has no CRS")
    return source.to_crs("EPSG:4326")


def download_sources(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    if list(raw_dir.glob("*.shp")):
        return
    archive = raw_dir / "conanp.zip"
    with requests.get(SOURCE_URLS["anp"], stream=True, timeout=300) as response:
        response.raise_for_status()
        with archive.open("wb") as fh:
            for block in response.iter_content(1024 * 1024):
                if block:
                    fh.write(block)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            if not member.is_dir():
                (raw_dir / Path(member.filename).name).write_bytes(zipped.read(member))
    archive.unlink()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-mexico")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(), lambda source: _load_source(source, raw_dir),
                        restrictions_dir)
