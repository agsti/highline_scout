from highliner.models.anchor import Anchor
from highliner.repositories.anchors import save_anchors, load_anchors


def test_to_geojson_points_and_sectors():
    from highliner.models.anchor import Anchor
    from highliner.router.serializers import anchors_to_geojson as to_geojson
    from highliner.core import geo
    a = Anchor(x=420000.0, y=4600000.0, elev=540.0,
               sectors=((80.0, 100.0, 35.0), (250.0, 280.0, 40.0)))
    fc = to_geojson([a])
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    feat = fc["features"][0]
    assert feat["geometry"]["type"] == "Point"
    lon, lat = feat["geometry"]["coordinates"]
    expected = geo.to_lonlat(a.x, a.y)
    assert (round(lon, 6), round(lat, 6)) == (round(expected[0], 6),
                                              round(expected[1], 6))
    assert feat["properties"]["elev"] == 540.0
    assert feat["properties"]["sectors"] == [[80.0, 100.0, 35.0],
                                             [250.0, 280.0, 40.0]]


def test_roundtrip(tmp_path):
    anchors = [
        Anchor(x=100.0, y=200.0, elev=540.5, sectors=((80.0, 100.0, 35.0),)),
        Anchor(x=150.0, y=210.0, elev=541.0,
               sectors=((250.0, 280.0, 40.0), (10.0, 30.0, 20.0))),
    ]
    path = tmp_path / "anchors.parquet"
    save_anchors(anchors, path)
    loaded = load_anchors(path)
    assert len(loaded) == 2
    assert loaded[0].sectors == ((80.0, 100.0, 35.0),)
    assert loaded[1].x == 150.0
    assert loaded[1].sectors[0] == (250.0, 280.0, 40.0)
