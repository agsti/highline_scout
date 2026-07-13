import json
from pathlib import Path

from highliner.models.anchor import Anchor


def save_anchors(anchors: list[Anchor], path: str | Path) -> None:
    import geopandas as gpd
    from shapely.geometry import Point

    from highliner.core import config
    rows = {
        "geometry": [Point(a.x, a.y) for a in anchors],
        "elev": [a.elev for a in anchors],
        "sectors": [json.dumps([list(s) for s in a.sectors]) for a in anchors],
    }
    gdf = gpd.GeoDataFrame(rows, crs=config.UTM_CRS)
    gdf.to_parquet(path)
