"""Fetch and normalize swisstopo swissALTI3D terrain for Switzerland.

swissALTI3D is a bare-earth elevation model published as 1 km square Cloud
Optimized GeoTIFFs in LV95/LN02 (EPSG:2056).  The STAC catalogue contains
historical snapshots, so each query keeps the newest 2 m asset for every tile.
Downloads are nodata-aware average-resampled to a persistent 5 m cache, matching
the extraction resolution and memory profile used by the rest of the pipeline.
"""
from __future__ import annotations

import concurrent.futures
import fcntl
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, TypedDict, cast

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.errors import RasterioError
from rasterio.transform import from_origin
from rasterio.warp import reproject

COLLECTION = "ch.swisstopo.swissalti3d"
ITEMS_URL = ("https://data.geo.admin.ch/api/stac/v1/collections/"
             f"{COLLECTION}/items")
CRS = "EPSG:2056"
SOURCE_RESOLUTION_M = 2.0
PROCESSING_RESOLUTION_M = 5.0
NODATA = -9999.0
HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}
_TIMEOUT_S = 180.0
_DOWNLOAD_WORKERS = 8
_RETRY_ATTEMPTS = 5
_RETRY_BASE_S = 2.0
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_TILE_RE = re.compile(r"^swissalti3d_\d{4}_(\d{4}-\d{4})$")

Bbox = tuple[float, float, float, float]


class TileAsset(TypedDict):
    """One downloadable swissALTI3D COG."""

    filename: str
    href: str


def fetch_swissalti_tiles(bbox: Bbox, cache_root: Path,
                          crs: str) -> list[Path]:
    """Return cached 5 m tiles intersecting ``bbox`` in EPSG:2056."""
    if crs != CRS:
        raise ValueError(f"swissALTI3D is available only in {CRS}")
    root = Path(cache_root)
    session = _session()
    assets = _cached_query_assets(session, bbox, crs, root)
    if not assets:
        return []
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(_DOWNLOAD_WORKERS, len(assets))) as pool:
        return list(pool.map(lambda asset: _ensure_tile(root, asset), assets))


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _bbox_lonlat(bbox: Bbox, crs: str) -> Bbox:
    transform = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    minx, miny, maxx, maxy = bbox
    corners = [transform.transform(x, y) for x, y in (
        (minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy))]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _query_assets(session: requests.Session, bbox: Bbox,
                  crs: str) -> list[TileAsset]:
    """Read all STAC pages and select the newest 2 m snapshot per tile."""
    lonlat = _bbox_lonlat(bbox, crs)
    params: dict[str, str] | None = {
        "bbox": ",".join(str(value) for value in lonlat),
        "limit": "100",
    }
    url: str | None = ITEMS_URL
    features: list[dict[str, Any]] = []
    while url is not None:
        page = _get_json(session, url, params)
        features.extend(cast(list[dict[str, Any]], page.get("features", [])))
        url = next((str(link["href"]) for link in page.get("links", [])
                    if link.get("rel") == "next"), None)
        params = None
    return _latest_assets(features)


def _get_json(session: requests.Session, url: str,
              params: dict[str, str] | None) -> dict[str, Any]:
    for attempt in range(_RETRY_ATTEMPTS):
        last = attempt == _RETRY_ATTEMPTS - 1
        try:
            response = session.get(url, params=params, timeout=_TIMEOUT_S)
            status = getattr(response, "status_code", 200)
            if status in _RETRY_STATUSES and not last:
                response.close()
                time.sleep(_retry_delay(attempt, response))
                continue
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except requests.RequestException as exc:
            if last:
                raise
            time.sleep(_retry_delay(attempt, exc.response))
    raise RuntimeError("unreachable")


def _retry_delay(attempt: int,
                 response: requests.Response | None = None) -> float:
    retry_after = 0.0
    if response is not None:
        try:
            retry_after = float(response.headers.get("Retry-After", 0) or 0)
        except ValueError:
            pass
    return max(retry_after, _RETRY_BASE_S * 2.0 ** attempt)


def _latest_assets(features: list[dict[str, Any]]) -> list[TileAsset]:
    """Choose the newest EPSG:2056 2 m COG for every stable tile id."""
    selected: dict[str, tuple[str, TileAsset]] = {}
    for feature in features:
        match = _TILE_RE.match(str(feature.get("id", "")))
        if match is None:
            continue
        tile_id = match.group(1)
        timestamp = str(feature.get("properties", {}).get("datetime", ""))
        for filename, value in feature.get("assets", {}).items():
            if not _is_two_metre_cog(filename, value):
                continue
            candidate: TileAsset = {
                "filename": filename,
                "href": str(value["href"]),
            }
            current = selected.get(tile_id)
            if current is None or timestamp > current[0]:
                selected[tile_id] = timestamp, candidate
    return [selected[tile][1] for tile in sorted(selected)]


def _is_two_metre_cog(filename: str, value: dict[str, Any]) -> bool:
    gsd = value.get("gsd", value.get("eo:gsd"))
    media_type = str(value.get("type", "")).lower()
    return (filename.lower().endswith(".tif")
            and gsd == SOURCE_RESOLUTION_M
            and value.get("proj:epsg") == 2056
            and "tiff" in media_type
            and bool(value.get("href")))


def _cached_query_assets(session: requests.Session, bbox: Bbox, crs: str,
                         cache_root: Path) -> list[TileAsset]:
    directory = cache_root / "swissalti3d_index"
    directory.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(json.dumps([crs, list(bbox)]).encode()).hexdigest()
    path = directory / f"{key}.json"
    if path.exists():
        return cast(list[TileAsset], json.loads(path.read_text()))
    lock_path = path.with_suffix(".lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            return cast(list[TileAsset], json.loads(path.read_text()))
        assets = _query_assets(session, bbox, crs)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(assets))
        tmp.replace(path)
    return assets


def _ensure_tile(cache_root: Path, asset: TileAsset) -> Path:
    directory = cache_root / "swissalti3d_5m"
    directory.mkdir(parents=True, exist_ok=True)
    source_name = Path(asset["filename"])
    dest = directory / f"{source_name.stem}_5m.tif"
    bounds = _asset_bounds(asset["filename"])
    if _valid_raster(dest, resolution=PROCESSING_RESOLUTION_M,
                     nodata=NODATA, bounds=bounds):
        return dest
    lock_path = dest.with_suffix(".tif.lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not _valid_raster(dest, resolution=PROCESSING_RESOLUTION_M,
                             nodata=NODATA, bounds=bounds):
            dest.unlink(missing_ok=True)
            source = dest.with_suffix(f".{os.getpid()}.source.tif")
            try:
                _download_tile(asset["href"], source, bounds=bounds)
                _resample_to_5m(source, dest)
            finally:
                source.unlink(missing_ok=True)
    return dest


def _asset_bounds(filename: str) -> Bbox:
    match = re.search(r"_(\d{4})-(\d{4})_2_2056_", filename)
    if match is None:
        raise ValueError(f"unrecognized swissALTI3D filename: {filename}")
    minx = float(int(match.group(1)) * 1000)
    miny = float(int(match.group(2)) * 1000)
    return minx, miny, minx + 1000.0, miny + 1000.0


def _valid_raster(path: Path, *, resolution: float, nodata: float,
                  bounds: Bbox | None = None) -> bool:
    """Confirm cached data is readable and has the expected grid metadata."""
    if not path.exists():
        return False
    try:
        with rasterio.open(path) as dataset:
            actual_bounds = tuple(dataset.bounds)
            valid = (
                dataset.count == 1
                and dataset.width > 0
                and dataset.height > 0
                and dataset.dtypes == ("float32",)
                and dataset.crs is not None
                and dataset.crs.to_epsg() == 2056
                and all(abs(value - resolution) < 1e-6
                        for value in dataset.res)
                and dataset.nodata == nodata
                and (bounds is None or all(
                    abs(actual - expected) < 1e-6
                    for actual, expected in zip(actual_bounds, bounds, strict=True)
                ))
            )
            if valid:
                dataset.read(1)
            return valid
    except (OSError, RasterioError, ValueError):
        return False


def _download_tile(url: str, dest: Path,
                   bounds: Bbox | None = None) -> None:
    part = dest.with_suffix(f".tif.{os.getpid()}.part")
    for attempt in range(_RETRY_ATTEMPTS):
        last = attempt == _RETRY_ATTEMPTS - 1
        part.unlink(missing_ok=True)
        try:
            with requests.get(url, headers=HEADERS, stream=True,
                              timeout=_TIMEOUT_S) as response:
                response.raise_for_status()
                with part.open("wb") as stream:
                    for block in response.iter_content(1024 * 1024):
                        if block:
                            stream.write(block)
            if not _valid_raster(
                    part, resolution=SOURCE_RESOLUTION_M, nodata=NODATA,
                    bounds=bounds):
                raise RuntimeError(
                    f"swissALTI3D did not return valid 2 m GeoTIFF data: {url}")
            part.replace(dest)
            return
        except (requests.RequestException, RuntimeError) as exc:
            if last:
                raise
            retry_response = exc.response if isinstance(
                exc, requests.RequestException) else None
            time.sleep(_retry_delay(attempt, retry_response))
        finally:
            part.unlink(missing_ok=True)
    raise RuntimeError("unreachable")


def _resample_to_5m(source: Path, dest: Path) -> None:
    """Average-resample one 2 m source tile onto its exact national 5 m grid."""
    with rasterio.open(source) as src:
        source_bounds = tuple(src.bounds)
        width = round((src.bounds.right - src.bounds.left)
                      / PROCESSING_RESOLUTION_M)
        height = round((src.bounds.top - src.bounds.bottom)
                       / PROCESSING_RESOLUTION_M)
        transform = from_origin(
            src.bounds.left, src.bounds.top,
            PROCESSING_RESOLUTION_M, PROCESSING_RESOLUTION_M)
        output = np.full((height, width), NODATA, dtype="float32")
        reproject(
            rasterio.band(src, 1), output,
            src_nodata=src.nodata, dst_nodata=NODATA,
            src_transform=src.transform, src_crs=src.crs,
            dst_transform=transform, dst_crs=src.crs,
            resampling=Resampling.average,
        )
        profile = {
            "driver": "GTiff", "width": width, "height": height,
            "count": 1, "dtype": "float32", "crs": src.crs,
            "nodata": NODATA, "transform": transform, "compress": "lzw",
        }
    part = dest.with_suffix(f".{os.getpid()}.part")
    try:
        with rasterio.open(part, "w", **profile) as dataset:
            dataset.write(output, 1)
        if not _valid_raster(
                part, resolution=PROCESSING_RESOLUTION_M, nodata=NODATA,
                bounds=source_bounds):
            raise RuntimeError(f"invalid derived swissALTI3D raster: {source}")
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; swissALTI3D tiles persist in the cache."""
    if cache_dir is None:
        raise ValueError("swissalti3d source requires cache_dir")
    return fetch_swissalti_tiles(bbox, cache_dir, crs)
