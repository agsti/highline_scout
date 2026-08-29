"""Luxembourg Natura 2000 and nationally protected-area source adapter."""
import argparse
import zipfile
from pathlib import Path
from typing import Final

import geopandas as gpd
import pandas as pd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "luxembourg"
__all__ = ["main", "shared"]
_DOWNLOAD_ROOT = "https://download.data.public.lu/resources"
SOURCE_URLS = {
    "zepa": (f"{_DOWNLOAD_ROOT}/natura-2000-zones-de-protection-speciale-"
             "zones-oiseaux/20260216-134115/ludo-20250613.zip"),
    "zec": (f"{_DOWNLOAD_ROOT}/natura-2000-zones-speciales-de-conservation-"
            "zones-habitats/20260216-134236/ludh-20250613.zip"),
    "enp": ("https://wms.inspire.geoportail.lu/geoserver/ps/wfs?"
            "service=WFS&version=1.0.0&request=GetFeature&"
            "typeName=ps:PS.ProtectedSitesNatureConservation-ZPIN"),
}
SOURCE_GLOBS = {
    "zepa": ("LUDO_*.shp",),
    "zec": ("LUDH_*.shp",),
    "enp": ("zpin.gml",),
}
_NAME_FIELDS = {
    "zepa": "SITENAME",
    "zec": "SITENAME",
    "enp": "sitename0_geographicalname_spelling0_spellingofname_text",
}
SPECS = {key: shared.LayerBuildSpec(key, key, _NAME_FIELDS[key],
                                    lambda props: True)
         for key in SOURCE_URLS}


def _download(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with dest.open("wb") as stream:
            for block in response.iter_content(1024 * 1024):
                if block:
                    stream.write(block)


def _extract(archive_path: Path, raw_dir: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if not member.is_dir():
                (raw_dir / Path(member.filename).name).write_bytes(
                    archive.read(member))


def download_sources(raw_dir: Path) -> None:
    """Cache official CC0 SPA, SAC, and ZPIN source files."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for key, patterns in SOURCE_GLOBS.items():
        if any(raw_dir.glob(patterns[0])):
            continue
        if key == "enp":
            _download(SOURCE_URLS[key], raw_dir / "zpin.gml")
            continue
        archive = raw_dir / f"{key}.zip"
        _download(SOURCE_URLS[key], archive)
        _extract(archive, raw_dir)
        archive.unlink()


def _load_source(key: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if key not in SOURCE_GLOBS:
        raise KeyError(key)
    paths = [path for pattern in SOURCE_GLOBS[key]
             for path in sorted(raw_dir.glob(pattern))]
    if not paths:
        raise FileNotFoundError(f"no {key} source in {raw_dir}")
    frames: list[gpd.GeoDataFrame] = []
    for path in paths:
        source = gpd.read_file(path)
        if source.crs is None:
            if key != "enp":
                raise ValueError(f"{path} has no CRS")
            # GeoServer's WFS 1.0 GML declares EPSG:3035 in an older URL form
            # that GDAL does not recognize, although all returned ZPIN
            # coordinates are explicitly in that CRS.
            source = source.set_crs("EPSG:3035")
        frames.append(source.to_crs("EPSG:4326"))
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-restrictions-luxembourg")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda key: _load_source(key, raw_dir), restrictions_dir)
