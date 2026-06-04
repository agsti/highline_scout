import math
from functools import lru_cache
from pyproj import Transformer
from highliner import config


@lru_cache(maxsize=2)
def _transformer(src: str, dst: str) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def to_lonlat(x: float, y: float) -> tuple[float, float]:
    return _transformer(config.UTM_CRS, config.WGS84_CRS).transform(x, y)


def to_utm(lon: float, lat: float) -> tuple[float, float]:
    return _transformer(config.WGS84_CRS, config.UTM_CRS).transform(lon, lat)


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


def bearing_in_sectors(angle: float, sectors, tol: float = 0.0) -> bool:
    for start, end, _drop in sectors:
        if _angular_contains(start - tol, end + tol, angle):
            return True
    return False
