"""FOEN protected-area source adapters for Switzerland."""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Final

import geopandas as gpd
import pandas as pd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "switzerland"
_DATA_ROOT = "https://data.geo.admin.ch"
SOURCE_URLS = {
    "game_reserves": (
        f"{_DATA_ROOT}/ch.bafu.bundesinventare-jagdbanngebiete/"
        "bundesinventare-jagdbanngebiete/"
        "bundesinventare-jagdbanngebiete_2056.shp.zip"),
    "bird_reserves": (
        f"{_DATA_ROOT}/ch.bafu.bundesinventare-vogelreservate/"
        "bundesinventare-vogelreservate/"
        "bundesinventare-vogelreservate_2056.shp.zip"),
    "parks": (
        f"{_DATA_ROOT}/ch.bafu.schutzgebiete-paerke_nationaler_bedeutung/"
        "schutzgebiete-paerke_nationaler_bedeutung/"
        "schutzgebiete-paerke_nationaler_bedeutung_2056.shp.zip"),
}
SOURCE_GLOBS: dict[str, tuple[str, ...]] = {
    "game_reserves": ("*jagdbann*.shp",),
    "bird_reserves": ("*wasserzugvogel*.shp",),
    "parks": ("*ParkPerimeter*.shp",),
}
DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}
SPECS = {
    "ch_game_reserves": shared.LayerBuildSpec(
        "ch_game_reserves", "game_reserves", "Name", lambda props: True),
    "ch_bird_reserves": shared.LayerBuildSpec(
        "ch_bird_reserves", "bird_reserves", "Name", lambda props: True),
    "ch_parks": shared.LayerBuildSpec(
        "ch_parks", "parks", "Name", lambda props: True),
}


def _load_source(source_key: str,
                 raw_dir: Path | None = None) -> gpd.GeoDataFrame:
    if source_key not in SOURCE_GLOBS:
        raise KeyError(source_key)
    base = raw_dir if raw_dir is not None else _default_raw_dir()
    frames: list[gpd.GeoDataFrame] = []
    for pattern in SOURCE_GLOBS[source_key]:
        for path in sorted(base.rglob(pattern)):
            source = gpd.read_file(path)
            if source.crs is None:
                raise ValueError(f"{path}: source has no CRS")
            frames.append(source.to_crs("EPSG:4326"))
    if not frames:
        raise FileNotFoundError(
            f"no {source_key} source in {base} "
            "(run `just etl-restriction switzerland`)")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True),
                            crs="EPSG:4326")


def _default_raw_dir() -> Path:
    return Path("data") / COUNTRY / "restrictions" / "raw"


def _has_source(raw_dir: Path, patterns: tuple[str, ...]) -> bool:
    """Return true only when every expected shapefile opens successfully."""
    for pattern in patterns:
        paths = sorted(raw_dir.glob(pattern))
        if not paths:
            return False
        for path in paths:
            try:
                source = gpd.read_file(path)
            except Exception:  # pyogrio/fiona expose backend-specific errors
                return False
            if source.crs is None:
                return False
    return True


def _extract_flattened(archive_path: Path, dest_dir: Path) -> None:
    """Extract files by basename, ignoring archive directory structure."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            (dest_dir / Path(member.filename).name).write_bytes(
                archive.read(member))


def _download(url: str, dest: Path) -> None:
    part = dest.with_suffix(f".{os.getpid()}.part")
    try:
        with requests.get(url, headers=DOWNLOAD_HEADERS, stream=True,
                          timeout=300) as response:
            response.raise_for_status()
            with part.open("wb") as stream:
                for block in response.iter_content(1024 * 1024):
                    if block:
                        stream.write(block)
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)


def download_sources(raw_dir: Path) -> None:
    """Atomically install missing, validated FOEN shapefile archives."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, patterns in SOURCE_GLOBS.items():
        source_dir = raw_dir / source
        if _has_source(source_dir, patterns):
            continue
        with tempfile.TemporaryDirectory(
                prefix=f".{source}.", suffix=".tmp", dir=raw_dir) as temp:
            staging = Path(temp)
            archive_path = staging / f"{source}.zip"
            extracted = staging / "extracted"
            _download(SOURCE_URLS[source], archive_path)
            _extract_flattened(archive_path, extracted)
            if not _has_source(extracted, patterns):
                raise RuntimeError(
                    f"downloaded {source} archive has no valid shapefile")
            if source_dir.exists():
                shutil.rmtree(source_dir)
            extracted.replace(source_dir)


def main(argv: list[str] | None = None) -> None:
    """Download and transform Switzerland's federal protected areas."""
    parser = argparse.ArgumentParser(prog="highliner-restrictions-switzerland")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir),
                        restrictions_dir)


if __name__ == "__main__":
    main()
