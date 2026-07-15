"""Read stored protected-area overlay layers (read side).

Country adapters build these files through ``highliner.etls.restriction``;
display metadata lives in ``highliner.core.restrictions``.
"""
from functools import lru_cache

import geopandas as gpd


@lru_cache(maxsize=32)
def load_layer(path_str: str) -> gpd.GeoDataFrame:
    """Read a stored layer (cached for the process); layers are small."""
    return gpd.read_parquet(path_str)
