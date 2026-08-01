"""SYKE protected-area source adapter for Finland.

The Finnish Environment Institute publishes Natura 2000 sites and three
national protected-area registers as open shapefile archives. Natura's SPA and
SCI attributes split the EU Birds and Habitats overlays; state, private and
wilderness reserves together form the national protected-area overlay.
"""
import argparse
import shutil
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import geopandas as gpd
import pandas as pd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "finland"
SOURCE_URLS = {
    "natura": "https://wwwd3.ymparisto.fi/d3/gis_data/spesific/natura.zip",
    "enp_state": ("https://wwwd3.ymparisto.fi/d3/gis_data/spesific/"
                  "luonnonsuojelualueet_valtio.zip"),
    "enp_private": ("https://wwwd3.ymparisto.fi/d3/gis_data/spesific/"
                    "luonnonsuojelualueet_yksityinen.zip"),
    "enp_wilderness": ("https://wwwd3.ymparisto.fi/d3/gis_data/spesific/"
                       "luonnonsuojelualueet_eramaa.zip"),
}
_SOURCE_DIRS = {"natura": ("natura",),
                "enp": ("enp_state", "enp_private", "enp_wilderness")}
_NAME_FIELDS = ("name", "Nimi", "NimiFin", "NATURA_NIMI", "NAME")


def _has_designation(props: Mapping[str, Any], key: str) -> bool:
    value = props.get(key)
    return isinstance(value, str) and bool(value.strip())


SPECS = {
    "zepa": shared.LayerBuildSpec(
        "zepa", "natura", "name", lambda props: _has_designation(props, "SPA")),
    "zec": shared.LayerBuildSpec(
        "zec", "natura", "name", lambda props: _has_designation(props, "SCI")),
    "enp": shared.LayerBuildSpec("enp", "enp", "name", lambda _props: True),
}


def _download(url: str, path: Path) -> None:
    part = path.with_suffix(".part")
    try:
        with requests.get(url, stream=True, timeout=300) as response:
            response.raise_for_status()
            with part.open("wb") as output:
                for block in response.iter_content(1024 * 1024):
                    if block:
                        output.write(block)
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)


def _extract(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(destination)


def download_sources(raw_dir: Path) -> None:
    """Download and unpack each authoritative SYKE archive once."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, url in SOURCE_URLS.items():
        destination = raw_dir / source
        if any(destination.rglob("*.shp")):
            continue
        archive = raw_dir / f"{source}.zip"
        _download(url, archive)
        staging = raw_dir / f".{source}.tmp"
        shutil.rmtree(staging, ignore_errors=True)
        try:
            _extract(archive, staging)
            staging.replace(destination)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            archive.unlink(missing_ok=True)


def _source_paths(source: str, raw_dir: Path) -> list[Path]:
    if source not in _SOURCE_DIRS:
        raise KeyError(f"unknown source: {source}")
    paths = [path for directory in _SOURCE_DIRS[source]
             for path in (raw_dir / directory).rglob("*.shp")]
    if source == "enp":
        paths.extend(raw_dir.glob("*.shp"))
    return sorted(set(paths))


def _name_column(frame: gpd.GeoDataFrame) -> str | None:
    return next((field for field in _NAME_FIELDS if field in frame.columns), None)


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    """Load a Finnish source and normalize its human-readable area name."""
    paths = _source_paths(source, raw_dir)
    if not paths:
        raise FileNotFoundError(f"no {source} source in {raw_dir}")
    frames: list[gpd.GeoDataFrame] = []
    for path in paths:
        frame = gpd.read_file(path)
        if frame.crs is None:
            raise ValueError(f"{path}: source has no CRS")
        name_field = _name_column(frame)
        frame["name"] = (frame[name_field].fillna("Finnish protected area").astype(str)
                         .str.strip() if name_field else "Finnish protected area")
        frames.append(frame.to_crs("EPSG:4326"))
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    """Download and transform Finland's Natura and protected-area overlays."""
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-finland")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir), restrictions_dir)
