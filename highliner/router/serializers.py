"""GeoJSON serialization of domain objects for the web boundary.

Conversion from internal UTM (EPSG:25831) to WGS84 lon/lat happens here, the
only place anchors and zones are turned into the FeatureCollections the
frontend consumes.
"""
from highliner.core import geo


def anchors_to_geojson(anchors) -> dict:
    features = []
    for a in anchors:
        lon, lat = geo.to_lonlat(a.x, a.y)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "elev": a.elev,
                "sectors": [list(s) for s in a.sectors],
            },
        })
    return {"type": "FeatureCollection", "features": features}


def zones_to_geojson(zones) -> dict:
    features = []
    for z in zones:
        ring = [list(geo.to_lonlat(x, y))
                for x, y in z.polygon.exterior.coords]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "height_min": z.height_min,
                "height_max": z.height_max,
                "n_anchors": z.n_anchors,
                "n_pairs": z.n_pairs,
            },
        })
    return {"type": "FeatureCollection", "features": features}
