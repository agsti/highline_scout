"""Shared request-handling helpers for the routers.

Holds the per-region anchor/raster cache, accessors for app-wide state stashed
on ``app.state`` by ``create_app``, and the bbox-parsing helpers that translate
``bbox`` / ``bbox_lonlat`` query params into UTM or lon/lat tuples.
"""
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, Request

from highliner.core import geo
from highliner.repositories.anchors import load_anchors
from highliner.models.raster import Raster


@lru_cache(maxsize=8)
def _load_region(data_dir_str: str, region: str):
    rdir = Path(data_dir_str) / region
    apath = rdir / "anchors.parquet"
    mpath = rdir / "mosaic.tif"
    if not apath.exists() or not mpath.exists():
        raise HTTPException(404, f"region '{region}' not found")
    return load_anchors(apath), Raster.open(mpath)


def load_region(request: Request, region: str):
    """Load (anchors, raster) for a region, cached per data_dir + region."""
    return _load_region(str(request.app.state.data_dir), region)


def get_data_dir(request: Request) -> Path:
    return request.app.state.data_dir


def get_jobstore(request: Request):
    return request.app.state.jobstore


def parse_bbox_utm(bbox, bbox_lonlat):
    """Return (minx, miny, maxx, maxy) in UTM from either a UTM bbox string
    or a lon/lat bbox string. Raises HTTPException(400) if neither given."""
    if bbox_lonlat:
        w, s, e, n = (float(v) for v in bbox_lonlat.split(","))
        minx, miny = geo.to_utm(w, s)
        maxx, maxy = geo.to_utm(e, n)
        return minx, miny, maxx, maxy
    if bbox:
        return tuple(float(v) for v in bbox.split(","))
    raise HTTPException(400, "provide bbox or bbox_lonlat")


def parse_bbox_lonlat(bbox, bbox_lonlat):
    """Return (w, s, e, n) in lon/lat from a lon/lat bbox string, or by
    converting a UTM bbox string's corners. Raises 400 if neither given."""
    if bbox_lonlat:
        return tuple(float(v) for v in bbox_lonlat.split(","))
    if bbox:
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
        w, s = geo.to_lonlat(minx, miny)
        e, n = geo.to_lonlat(maxx, maxy)
        return w, s, e, n
    raise HTTPException(400, "provide bbox or bbox_lonlat")
