"""Shared test fixtures' helpers.

Nothing here may be imported by `highliner/` — this is the tests' side of the
line, and the dead-code scan (`just deadcode`) relies on that split to tell
product code apart from code only its own tests keep alive.
"""

from highliner.core import config, geo


def to_utm(lon: float, lat: float) -> tuple[float, float]:
    """Lon/lat to the project's UTM zone, for writing fixtures in map coords."""
    return geo.from_lonlat_crs(lon, lat, config.UTM_CRS)
