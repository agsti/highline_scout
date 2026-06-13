import json

from highliner.models.anchor import Anchor


def save_anchors(anchors, path):
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


def load_anchors(path) -> list[Anchor]:
    import geopandas as gpd
    gdf = gpd.read_parquet(path)
    out = []
    for geom, elev, sectors in zip(gdf.geometry, gdf.elev, gdf.sectors):
        secs = tuple(tuple(s) for s in json.loads(sectors))
        out.append(Anchor(x=geom.x, y=geom.y, elev=float(elev), sectors=secs))
    return out
