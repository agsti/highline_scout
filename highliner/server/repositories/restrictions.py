"""Read stored protected-area overlay layers (read side).

The build side (``fetch_all``) lives in
``highliner.etl.repositories.restrictions`` and the ``LAYERS`` registry both
sides consume lives in ``highliner.core.restrictions``.
"""
from functools import lru_cache

import geopandas as gpd


@lru_cache(maxsize=32)
def load_layer(path_str: str) -> gpd.GeoDataFrame:
    """Read a stored layer (cached for the process); layers are small."""
    return gpd.read_parquet(path_str)
