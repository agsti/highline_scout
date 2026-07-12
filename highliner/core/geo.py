import math
from functools import lru_cache
from typing import Any

from pyproj import Transformer

from highliner.core import config


@lru_cache(maxsize=32)
def _transformer(src: str, dst: str) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def to_lonlat(x: float, y: float) -> tuple[float, float]:
    return _transformer(config.UTM_CRS, config.WGS84_CRS).transform(x, y)


def to_utm(lon: float, lat: float) -> tuple[float, float]:
    return _transformer(config.WGS84_CRS, config.UTM_CRS).transform(lon, lat)


def to_lonlat_crs(x: float, y: float, crs: str) -> tuple[float, float]:
    return _transformer(crs, config.WGS84_CRS).transform(x, y)


def from_lonlat_crs(lon: float, lat: float, crs: str) -> tuple[float, float]:
    return _transformer(config.WGS84_CRS, crs).transform(lon, lat)


def reproject_xy(xs: Any, ys: Any, src_crs: str, dst_crs: str) -> tuple[Any, Any]:
    """Transform coordinate arrays from ``src_crs`` to ``dst_crs`` in one call."""
    return _transformer(src_crs, dst_crs).transform(xs, ys)


def bearing(x1: float, y1: float, x2: float, y2: float) -> float:
    """Clockwise bearing from north, degrees in [0, 360)."""
    deg = math.degrees(math.atan2(x2 - x1, y2 - y1))
    return deg % 360.0


def _angular_contains(start: float, end: float, angle: float) -> bool:
    """Is `angle` within the clockwise arc start->end (handles 0/360 wrap)?"""
    start %= 360.0
    end %= 360.0
    angle %= 360.0
    if start <= end:
        return start <= angle <= end
    return angle >= start or angle <= end


def bearing_in_sectors(angle: float,
                       sectors: tuple[tuple[float, float, float], ...],
                       tol: float = 0.0) -> bool:
    for start, end, _drop in sectors:
        # Widening a near-full-circle sector by tol would wrap the arc past
        # 360 and normalize into a tiny sliver, inverting the test. If the
        # widened span covers the whole circle, accept every bearing instead.
        if (end - start) % 360.0 + 2 * tol >= 360.0:
            return True
        if _angular_contains(start - tol, end + tol, angle):
            return True
    return False
