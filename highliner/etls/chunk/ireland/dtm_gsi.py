"""Fetch GSI's CC-BY 1 m bare-earth LiDAR DTM archives for Ireland.

GSI's official coverage service indexes each downloadable 7z survey archive.
The Phase 2 coverage is currently the contiguous central-Ireland survey area;
its 1 m GeoTIFFs are cached after conversion to the pipeline's 5 m grid.
"""
import fcntl
import json
import subprocess
import time
from pathlib import Path
from typing import Any, cast

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.warp import reproject
from shapely.geometry import box, shape

from highliner.etls.chunk.dtm_core import NODATA, _bbox_geom_lonlat

Bbox = tuple[float, float, float, float]
_SERVICE = ("https://gsi.geodata.gov.ie/server/rest/services/Lidar/"
            "IE_GSI_LiDAR_Coverage_GSI_Phase2_IE26_ITM/FeatureServer/12/query")
_ATTEMPTS = 4
_RES = 5.0
_CATALOG_ROOT: Path | None = None


def _download_catalog() -> dict[str, Any]:
    """Download every official GSI Phase 2 coverage feature."""
    features: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "where": "1=1", "outFields": "DATA_NAME,DATA_URL,RESOLUTION",
            "returnGeometry": "true", "resultOffset": str(offset),
            "resultRecordCount": "2000", "f": "geojson",
        }
        response = requests.get(_SERVICE, params=params, timeout=300)
        response.raise_for_status()
        page = response.json()
        batch = page.get("features", [])
        if not isinstance(batch, list):
            raise RuntimeError("GSI coverage catalogue has no feature list")
        features.extend(batch)
        if not page.get("exceededTransferLimit") or not batch:
            break
        offset += len(batch)
    if not features:
        raise RuntimeError("GSI coverage catalogue contained no LiDAR archives")
    return {"type": "FeatureCollection", "features": features}


def _load_catalog(root: Path) -> dict[str, Any]:
    """Cache the GSI coverage catalogue, shared safely by worker processes."""
    path = root / "catalog.json"
    if path.exists():
        return cast(dict[str, Any], json.loads(path.read_text()))
    root.mkdir(parents=True, exist_ok=True)
    with (root / "catalog.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not path.exists():
            part = path.with_suffix(".part")
            part.write_text(json.dumps(_download_catalog()))
            part.replace(path)
    return cast(dict[str, Any], json.loads(path.read_text()))


def _catalog() -> dict[str, Any]:
    """Load the configured process-local cache of coverage features."""
    if _CATALOG_ROOT is None:
        raise RuntimeError("GSI catalogue cache root has not been configured")
    return _load_catalog(_CATALOG_ROOT)


def _intersects(feature: dict[str, Any], bbox_: Bbox) -> bool:
    geometry = feature.get("geometry")
    if not geometry:
        return False
    if "rings" in geometry:
        geometry = {"type": "Polygon", "coordinates": geometry["rings"]}
        return bool(shape(geometry).intersects(box(*bbox_)))
    return bool(shape(geometry).intersects(
        _bbox_geom_lonlat(bbox_, "EPSG:2157")))


def _properties(feature: dict[str, Any]) -> dict[str, str]:
    """Return attributes from either GeoJSON or ArcGIS REST feature shapes."""
    props = feature.get("properties") or feature.get("attributes") or {}
    return {str(key): str(value) for key, value in props.items()}


def _download(url: str, path: Path) -> None:
    for attempt in range(_ATTEMPTS):
        try:
            with requests.get(url, stream=True, timeout=300) as response:
                response.raise_for_status()
                with path.open("wb") as output:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            output.write(chunk)
            return
        except requests.RequestException:
            path.unlink(missing_ok=True)
            if attempt == _ATTEMPTS - 1:
                raise
            time.sleep(2.0 ** attempt)


def _resample(raw: Path, dest: Path) -> None:
    """Average a 1 m DTM to a cached 5 m GeoTIFF, preserving source nodata."""
    with rasterio.open(raw) as source:
        scale = _RES / source.res[0]
        width = round(source.width / scale)
        height = round(source.height / scale)
        data = np.full((height, width), NODATA, dtype="float32")
        transform = source.transform * source.transform.scale(scale, scale)
        reproject(rasterio.band(source, 1), data, src_nodata=source.nodata,
                  dst_nodata=NODATA, dst_transform=transform,
                  dst_crs=source.crs, resampling=Resampling.average)
        profile = source.profile
    profile.update(driver="GTiff", width=width, height=height, count=1,
                   dtype="float32", nodata=NODATA, transform=transform,
                   compress="lzw")
    part = dest.with_suffix(".part")
    with rasterio.open(part, "w", **profile) as output:
        output.write(data, 1)
    part.replace(dest)


def _materialize(url: str, name: str, root: Path) -> Path:
    """Download one archive once and retain only its 5 m bare-earth raster."""
    dest = root / f"{name}.tif"
    if dest.exists():
        return dest
    with (root / f"{name}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if dest.exists():
            return dest
        archive = root / f"{name}.7z.part"
        extracted = root / f"{name}.raw"
        extracted.mkdir(exist_ok=True)
        try:
            _download(url, archive)
            subprocess.run(["7z", "x", f"-o{extracted}", str(archive)],
                           check=True, capture_output=True)
            raw = next(extracted.rglob("*.tif"))
            _resample(raw, dest)
        finally:
            archive.unlink(missing_ok=True)
            for path in sorted(extracted.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            extracted.rmdir()
    return dest


def fetch_gsi_lidar(bbox: Bbox, cache_root: Path, crs: str) -> list[Path]:
    """Return cached 5 m GSI DTM sheets intersecting a chunk in Irish TM."""
    if crs != "EPSG:2157":
        raise ValueError("GSI LiDAR DTM is available only in EPSG:2157")
    root = cache_root / "gsi-lidar-1m"
    root.mkdir(parents=True, exist_ok=True)
    catalog = _catalog()
    return [_materialize(_properties(feature)["DATA_URL"],
                         _properties(feature)["DATA_NAME"], root)
            for feature in catalog["features"] if _intersects(feature, bbox)]


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Module-level multiprocessing-safe fetcher for ``gsi_lidar_dtm_1m``."""
    if cache_dir is None:
        raise ValueError("gsi_lidar_dtm_1m requires cache_dir")
    root = cache_dir / "gsi-lidar-1m"
    root.mkdir(parents=True, exist_ok=True)
    global _CATALOG_ROOT
    original = _CATALOG_ROOT
    _CATALOG_ROOT = root
    try:
        return fetch_gsi_lidar(bbox, cache_dir, crs)
    finally:
        _CATALOG_ROOT = original
