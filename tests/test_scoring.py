from highliner.anchors import Anchor
from highliner.pairing import Candidate
from highliner import scoring


def make_cand(exposure, dh, length):
    a = Anchor(0, 0, 100, ((80, 100, 60),))
    b = Anchor(length, 0, 100 - dh, ((260, 280, 60),))
    return Candidate(a=a, b=b, length=length, exposure=exposure, height_diff=dh)


def test_more_exposure_scores_higher():
    low = make_cand(30, 0, 50)
    high = make_cand(80, 0, 50)
    assert scoring.score(high) > scoring.score(low)


def test_geojson_structure():
    fc = scoring.to_geojson([make_cand(50, 2, 40)])
    assert fc["type"] == "FeatureCollection"
    feat = fc["features"][0]
    assert feat["geometry"]["type"] == "LineString"
    assert len(feat["geometry"]["coordinates"]) == 2
    props = feat["properties"]
    assert {"length", "exposure", "height_diff", "score"} <= props.keys()
    # coordinates are lon/lat (roughly within Catalonia / valid lon-lat range)
    for lon, lat in feat["geometry"]["coordinates"]:
        assert -180 <= lon <= 180 and -90 <= lat <= 90
