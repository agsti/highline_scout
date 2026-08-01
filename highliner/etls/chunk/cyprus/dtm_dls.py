"""Fetch the Cyprus DLS 2019 one-metre bare-earth DTM sheets.

The Department of Lands and Surveys publishes individual GeoTIFF sheets in
ETRS89 geographic coordinates. Their directory is cached as a lightweight
metadata index; selected source sheets are cached, then reprojected to 5 m
UTM 36N GeoTIFFs for the shared terrain pipeline.
"""
import concurrent.futures
import fcntl
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TypedDict, cast

import rasterio
import requests
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject
from shapely.geometry import box

from highliner.etls.chunk.dtm_core import NODATA

DIRECTORY_URL = "https://eservices.dls.moi.gov.cy/inspire_downloads/EL/rasters/2019_DTM/"
SOURCE_CRS = "EPSG:4258"
CRS = "EPSG:32636"
SOURCE_NODATA = -3.4028230607370965e38
_ATTEMPTS = 4
_HREF = re.compile(r'href="([^"]+\.tif\.xml)"', re.IGNORECASE)
Bbox = tuple[float, float, float, float]


class Sheet(TypedDict):
    name: str
    bbox: list[float]


def _get(url: str) -> requests.Response:
    for attempt in range(_ATTEMPTS):
        try:
            response = requests.get(url, timeout=300)
            response.raise_for_status()
            return response
        except requests.RequestException:
            if attempt == _ATTEMPTS - 1:
                raise
            time.sleep(2.0 ** attempt)
    raise RuntimeError("unreachable")


def _parse_sheet_metadata(name: str, content: bytes) -> Sheet:
    root = ET.fromstring(content)
    extent = next(element for element in root.iter()
                  if element.tag.rsplit("}", 1)[-1] == "GeoBndBox")
    values = {element.tag.rsplit("}", 1)[-1]: float(element.text or "nan")
              for element in extent}
    return {"name": name.removesuffix(".xml"),
            "bbox": [values["westBL"], values["southBL"],
                     values["eastBL"], values["northBL"]]}


def _metadata_sheet(name: str) -> Sheet:
    return _parse_sheet_metadata(name, _get(DIRECTORY_URL + name).content)


def _load_index(root: Path) -> list[Sheet]:
    path = root / "index.json"
    if path.exists():
        return cast(list[Sheet], json.loads(path.read_text()))
    root.mkdir(parents=True, exist_ok=True)
    with (root / "index.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            return cast(list[Sheet], json.loads(path.read_text()))
        names = sorted(set(_HREF.findall(_get(DIRECTORY_URL).text)))
        if not names:
            raise RuntimeError("Cyprus DLS DTM directory contained no sheet metadata")
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            sheets = list(pool.map(_metadata_sheet, names))
        temp = path.with_suffix(f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(sheets))
        temp.replace(path)
    return sheets


def _bbox_lonlat(bbox: Bbox) -> tuple[float, float, float, float]:
    transform = Transformer.from_crs(CRS, SOURCE_CRS, always_xy=True)
    minx, miny, maxx, maxy = bbox
    corners = [transform.transform(x, y) for x, y in
               ((minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy))]
    xs, ys = zip(*corners, strict=True)
    return min(xs), min(ys), max(xs), max(ys)


def _download_sheet(root: Path, name: str) -> Path:
    dest = root / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    root.mkdir(parents=True, exist_ok=True)
    with dest.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not dest.exists() or dest.stat().st_size == 0:
            temp = dest.with_suffix(f".{os.getpid()}.part")
            temp.write_bytes(_get(DIRECTORY_URL + name).content)
            temp.replace(dest)
    return dest


def _reproject(source: Path, dest: Path) -> Path:
    with rasterio.open(source) as src:
        transform, width, height = calculate_default_transform(
            src.crs, CRS, src.width, src.height, *src.bounds, resolution=5)
        profile = src.profile | {"crs": CRS, "transform": transform,
                                 "width": width, "height": height,
                                 "nodata": NODATA, "compress": "deflate"}
        with rasterio.open(dest, "w", **profile) as output:
            reproject(rasterio.band(src, 1), rasterio.band(output, 1),
                      src_transform=src.transform, src_crs=src.crs,
                      src_nodata=SOURCE_NODATA, dst_transform=transform,
                      dst_crs=CRS, dst_nodata=NODATA,
                      resampling=Resampling.bilinear)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Return DLS sheets intersecting ``bbox``, reprojected for analysis."""
    if crs != CRS:
        raise ValueError(f"Cyprus DLS DTM is processed only in {CRS}")
    if cache_dir is None:
        raise ValueError("dls_dtm_2019 source requires cache_dir")
    root = Path(cache_dir) / "dls_dtm_2019"
    wanted = box(*_bbox_lonlat(bbox))
    sources = [_download_sheet(root / "source", sheet["name"])
               for sheet in _load_index(root)
               if box(*sheet["bbox"]).intersects(wanted)]
    tiles = Path(tiles_dir)
    tiles.mkdir(parents=True, exist_ok=True)
    return [_reproject(source, tiles / source.name) for source in sources]
