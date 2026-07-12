import json
from pathlib import Path

from highliner.models.anchor import Anchor


def load_anchors(path: str | Path) -> list[Anchor]:
    import geopandas as gpd
    gdf = gpd.read_parquet(path)
    out = []
    for geom, elev, sectors in zip(
            gdf.geometry, gdf.elev, gdf.sectors, strict=True):
        secs: tuple[tuple[float, float, float], ...] = tuple(
            tuple(s) for s in json.loads(sectors))
        out.append(Anchor(x=geom.x, y=geom.y, elev=float(elev), sectors=secs))
    return out
