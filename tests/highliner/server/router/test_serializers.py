from highliner.models.anchor import Anchor
from highliner.server.router.serializers import anchors_to_geojson

from highliner.core import geo


def test_to_geojson_points_and_sectors() -> None:
    anchor = Anchor(
        x=420000.0, y=4600000.0, elev=540.0,
        sectors=((80.0, 100.0, 35.0), (250.0, 280.0, 40.0)))

    feature_collection = anchors_to_geojson([anchor])

    assert feature_collection["type"] == "FeatureCollection"
    assert len(feature_collection["features"]) == 1
    feature = feature_collection["features"][0]
    assert feature["geometry"]["type"] == "Point"
    lon, lat = feature["geometry"]["coordinates"]
    expected = geo.to_lonlat(anchor.x, anchor.y)
    assert (round(lon, 6), round(lat, 6)) == (
        round(expected[0], 6), round(expected[1], 6))
    assert feature["properties"]["elev"] == 540.0
    assert feature["properties"]["sectors"] == [
        [80.0, 100.0, 35.0], [250.0, 280.0, 40.0]]
