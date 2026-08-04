"""Fetch Lantmäteriet's 1 m bare-earth terrain COGs through its STAC API."""
from __future__ import annotations

import hashlib
import os
from functools import partial
from pathlib import Path

import requests
from pyproj import Transformer

from highliner.etls.chunk.dtm_core import _download_with_retries

STAC_SEARCH_URL = "https://api.lantmateriet.se/stac-hojd/v1/search"
CRS = "EPSG:3006"
_TIMEOUT_S = 300

Bbox = tuple[float, float, float, float]


def _credentials() -> tuple[str, str]:
    username = os.environ.get("HIGHLINER_LANTMATERIET_USERNAME")
    password = os.environ.get("HIGHLINER_LANTMATERIET_PASSWORD")
    if not username or not password:
        raise RuntimeError("set HIGHLINER_LANTMATERIET_USERNAME and "
                           "HIGHLINER_LANTMATERIET_PASSWORD after ordering "
                           "free Markhöjdmodell access from Lantmäteriet")
    return username, password


def _lonlat_bbox(bbox: Bbox) -> Bbox:
    transform = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    minx, miny, maxx, maxy = bbox
    corners = [transform.transform(x, y) for x, y in (
        (minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy))]
    xs, ys = zip(*corners, strict=True)
    return min(xs), min(ys), max(xs), max(ys)


def _terrain_urls(bbox: Bbox) -> list[str]:
    lonlat = _lonlat_bbox(bbox)
    response = requests.get(STAC_SEARCH_URL, params={
        "bbox": ",".join(str(value) for value in lonlat), "limit": "100"},
        timeout=_TIMEOUT_S)
    response.raise_for_status()
    payload = response.json()
    urls: set[str] = set()
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        asset = feature.get("assets", {}).get("data", {})
        if (properties.get("hojdmodelltyp") == "markhöjdmodell"
                and properties.get("geometriskupplosning") == 1
                and isinstance(asset.get("href"), str)):
            urls.add(asset["href"])
    return sorted(urls)


def _download(url: str, dest: Path, credentials: tuple[str, str]) -> Path:
    response = requests.get(url, auth=credentials, timeout=_TIMEOUT_S)
    response.raise_for_status()
    dest.write_bytes(response.content)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Return authenticated Lantmäteriet terrain COGs intersecting ``bbox``."""
    if crs != CRS:
        raise RuntimeError(f"Lantmäteriet Markhöjdmodell is published in {CRS}")
    credentials = _credentials()
    root = Path(cache_dir) if cache_dir is not None else Path(tiles_dir)
    root = root / "lantmateriet_markhojdmodell"
    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for url in _download_with_retries(lambda: _terrain_urls(bbox)):
        dest = root / f"{hashlib.sha256(url.encode()).hexdigest()}.tif"
        if not dest.exists() or not dest.stat().st_size:
            _download_with_retries(partial(_download, url, dest, credentials))
        paths.append(dest)
    return paths
