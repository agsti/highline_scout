"""Fetch DAF's lidar-derived bare-earth MNTs for French Polynesia.

The Direction des affaires foncieres publishes these 2015 lidar-derived MNTs
under CC BY on data.gouv.fr. They are 1 m GeoTIFFs in their local RGPF UTM
zones; ``-1`` denotes the sea and outside the surveyed land, and is converted
to the pipeline sea sentinel before any terrain analysis. Each is cached once
per country and read locally by every chunk worker.
"""
import fcntl
import math
import os
from dataclasses import dataclass
from pathlib import Path

import rasterio
import requests
from rasterio.enums import Resampling

from highliner.etls.chunk.dtm_core import SEA_SENTINEL, _download_with_retries

NODATA = -1.0
_MOOREA_URL = (
    "https://static.data.gouv.fr/resources/modeles-numerique-de-terrain-mnt-"
    "des-iles-de-la-polyensie-francaise/20200428-004604/mnt-idv-moo-2015-0.tiff"
)
_TAHITI_URL = (
    "https://static.data.gouv.fr/resources/modeles-numerique-de-terrain-mnt-"
    "des-iles-de-la-polynesie-francaise/20200430-210339/mnt-idv-tht-2015-0.tiff"
)
_BORA_BORA_URL = (
    "https://static.data.gouv.fr/resources/modeles-numerique-de-terrain-mnt-"
    "des-iles-de-la-polyensie-francaise/20200428-002730/mnt-islv-bor-2015-0.tiff"
)

Bbox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Source:
    """One DAF lidar MNT and its native island extent."""

    name: str
    url: str
    bbox: Bbox
    crs: str


SOURCES = (
    Source("moorea", _MOOREA_URL, (188000, 8050000, 209000, 8067000), "EPSG:3297"),
    Source("tahiti", _TAHITI_URL, (220000, 8034000, 247000, 8067000), "EPSG:3297"),
    Source("bora_bora", _BORA_BORA_URL, (628000, 8168000, 641000, 8183000),
           "EPSG:3296"),
)


def _source_for(bbox: Bbox, crs: str) -> Source:
    for source in SOURCES:
        if source.crs == crs and source.bbox[0] < bbox[2] and bbox[0] < source.bbox[2] \
                and source.bbox[1] < bbox[3] and bbox[1] < source.bbox[3]:
            return source
    raise RuntimeError(f"no DAF lidar MNT covers {bbox} in {crs}")


def _cache_path(cache_dir: Path, source: Source) -> Path:
    return Path(cache_dir) / f"{source.name}.tif"


def _resample_and_mask(source_path: Path, dest: Path) -> None:
    """Convert the 1 m source to the pipeline's 5 m grid without a huge RAM peak."""
    with rasterio.open(source_path) as source:
        width = math.ceil(source.width / 5)
        height = math.ceil(source.height / 5)
        data = source.read(1, out_shape=(height, width),
                           resampling=Resampling.average).astype("float32")
        profile = source.profile
    data[data == NODATA] = SEA_SENTINEL
    profile.update(driver="GTiff", dtype="float32", nodata=SEA_SENTINEL,
                   width=width, height=height,
                   transform=source.transform * source.transform.scale(
                       source.width / width, source.height / height),
                   compress="deflate")
    with rasterio.open(dest, "w", **profile) as output:
        output.write(data, 1)


def _download(cache_dir: Path, source: Source) -> Path:
    dest = _cache_path(cache_dir, source)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    cache_dir.mkdir(parents=True, exist_ok=True)
    with dest.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        source_path = dest.with_suffix(f".source.{os.getpid()}.tmp")
        try:
            with requests.get(source.url, stream=True, timeout=900) as response:
                response.raise_for_status()
                with source_path.open("wb") as output:
                    for block in response.iter_content(1024 * 1024):
                        if block:
                            output.write(block)
            temp = dest.with_suffix(f".{os.getpid()}.tmp")
            _resample_and_mask(source_path, temp)
            temp.replace(dest)
        finally:
            source_path.unlink(missing_ok=True)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Return the cached island MNT covering a chunk in its native CRS."""
    del tiles_dir
    if cache_dir is None:
        raise RuntimeError("DAF MNT requires a persistent country cache directory")
    source = _source_for(bbox, crs)
    return [_download_with_retries(lambda: _download(Path(cache_dir), source))]
