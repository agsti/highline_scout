"""Known region defaults for precompute.

The current production data was built for Catalonia from ICGC in EPSG:25831.
Spain-wide regions use the national IGN/IDEE MDT05 coverage in the CRS exposed
by that service.
"""

from dataclasses import dataclass
from pathlib import Path

from highliner.core import config


@dataclass(frozen=True)
class RegionDefaults:
    crs: str
    dtm_source: str
    country: str


_PENINSULA_AND_BALEARICS = RegionDefaults(
    crs="EPSG:25830", dtm_source="cnig", country="spain")
_CANARIES = RegionDefaults(crs="EPSG:4083", dtm_source="cnig", country="spain")
_CATALONIA = RegionDefaults(
    crs=config.UTM_CRS, dtm_source="icgc", country="spain")


REGION_DEFAULTS: dict[str, RegionDefaults] = {
    "catalonia": _CATALONIA,
    "catalunya": _CATALONIA,
    "andalucia": _PENINSULA_AND_BALEARICS,
    "aragon": _PENINSULA_AND_BALEARICS,
    "asturias": _PENINSULA_AND_BALEARICS,
    "cantabria": _PENINSULA_AND_BALEARICS,
    "castilla_la_mancha": _PENINSULA_AND_BALEARICS,
    "castilla_y_leon": _PENINSULA_AND_BALEARICS,
    "ceuta": _PENINSULA_AND_BALEARICS,
    "comunitat_valenciana": _PENINSULA_AND_BALEARICS,
    "extremadura": _PENINSULA_AND_BALEARICS,
    "galicia": _PENINSULA_AND_BALEARICS,
    "illes_balears": _PENINSULA_AND_BALEARICS,
    "la_rioja": _PENINSULA_AND_BALEARICS,
    "madrid": _PENINSULA_AND_BALEARICS,
    "melilla": _PENINSULA_AND_BALEARICS,
    "murcia": _PENINSULA_AND_BALEARICS,
    "navarra": _PENINSULA_AND_BALEARICS,
    "pais_vasco": _PENINSULA_AND_BALEARICS,
    "canarias": _CANARIES,
}


def defaults_for_region(region: str) -> RegionDefaults:
    return REGION_DEFAULTS.get(region, _CATALONIA)


def country_for_region(region: str) -> str:
    """The country a region belongs to (used as the top-level data/cache
    partition). Unknown regions default to the shipped Catalonia/Spain data."""
    return defaults_for_region(region).country


def region_dir(data_dir: Path | str, region: str) -> Path:
    """On-disk directory for a region's outputs: ``<data_dir>/<country>/<region>``."""
    return Path(data_dir) / country_for_region(region) / region
