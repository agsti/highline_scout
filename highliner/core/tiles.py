"""Slippy-map (web-mercator) tile math for the density pyramid.

Cells are OSM/Leaflet tiles ``(z, xtile, ytile)``. Shared by the offline density
builder and the ``/density`` endpoint so both agree on cell <-> lon/lat.
"""
import math


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    """Tile ``(xtile, ytile)`` containing ``(lon, lat)`` at zoom ``z``."""
    n = 2 ** z
    xtile = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    xtile = min(max(xtile, 0), n - 1)
    ytile = min(max(ytile, 0), n - 1)
    return xtile, ytile


def tile_bounds_lonlat(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Geographic bounds ``(west, south, east, north)`` of tile ``(z, x, y)``."""
    n = 2 ** z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + 1) / n))))
    return west, south, east, north
