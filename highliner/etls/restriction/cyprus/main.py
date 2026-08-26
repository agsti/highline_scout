"""Cyprus Natura 2000 and nationally-designated-area adapter."""
import argparse
import zipfile
from pathlib import Path
from typing import Final
from urllib.request import urlretrieve

import geopandas as gpd

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "cyprus"
SOURCE_URLS = {
    "natura": "https://data.gov.cy/sites/default/files/Natura2000_ETRS_0.zip",
    "national": "https://data.gov.cy/sites/default/files/cy_cdda_v23_2025_polygon.zip",
}
SPECS = {
    "zepa": shared.LayerBuildSpec(
        "zepa", "natura", "naturaname",
        lambda props: str(props.get("designatio", "")).upper() == "SPA"),
    "zec": shared.LayerBuildSpec(
        "zec", "natura", "naturaname",
        lambda props: str(props.get("designatio", "")).upper() in {"SCI", "SAC"}),
    "enp": shared.LayerBuildSpec("enp", "national", "SITENAME", lambda props: True),
}


def _download_sources(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for key, url in SOURCE_URLS.items():
        if any(raw_dir.glob(f"{key}_*.shp")):
            continue
        archive = raw_dir / f"{key}.zip"
        urlretrieve(url, archive)
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                if not member.is_dir():
                    (raw_dir / f"{key}_{Path(member.filename).name}").write_bytes(
                        bundle.read(member))
        archive.unlink()


def _load_source(key: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if key not in SOURCE_URLS:
        raise KeyError(key)
    path = next(raw_dir.glob(f"{key}_*.shp"), None)
    if path is None:
        raise FileNotFoundError(f"no {key} shapefile in {raw_dir}")
    return gpd.read_file(path).to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-restrictions-cyprus")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    raw_dir = args.data_dir / COUNTRY / "restrictions" / "raw"
    _download_sources(raw_dir)
    shared.write_layers(SPECS.values(), lambda key: _load_source(key, raw_dir),
                        raw_dir.parent)
