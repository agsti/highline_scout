from highliner import geo
from highliner.pairing import Candidate


def score(c: Candidate) -> float:
    """Higher = better. Reward exposure, penalize height difference."""
    return round(c.exposure - 2.0 * c.height_diff, 2)


def to_geojson(candidates) -> dict:
    features = []
    for c in sorted(candidates, key=score, reverse=True):
        a_lon, a_lat = geo.to_lonlat(c.a.x, c.a.y)
        b_lon, b_lat = geo.to_lonlat(c.b.x, c.b.y)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[a_lon, a_lat], [b_lon, b_lat]],
            },
            "properties": {
                "length": c.length,
                "exposure": c.exposure,
                "height_diff": c.height_diff,
                "score": score(c),
            },
        })
    return {"type": "FeatureCollection", "features": features}
