from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.services import zones


def make_pair(x1: float, x2: float, y: float, exposure: float) -> Candidate:
    """A valid facing pair along the x axis at row y."""
    a = Anchor(x=x1, y=y, elev=100.0, sectors=((80, 100, 60),))
    b = Anchor(x=x2, y=y, elev=100.0, sectors=((260, 280, 60),))
    return Candidate(a=a, b=b, length=abs(x2 - x1),
                     exposure=exposure, height_diff=0.0)


def test_empty_candidates_no_zones() -> None:
    assert zones.build_zones([]) == []


def test_single_pair_is_one_zone() -> None:
    [z] = zones.build_zones([make_pair(0, 80, 0, exposure=60.0)])
    assert z.n_anchors == 2
    assert z.n_pairs == 1
    assert z.height_min == z.height_max == 60.0
    # 2-point hull is a line; the buffer must still yield a real polygon
    assert z.polygon.geom_type == "Polygon"
    assert z.polygon.area > 0


def test_far_pairs_make_separate_zones() -> None:
    cands = [make_pair(0, 80, 0, exposure=60.0),
             make_pair(0, 80, 10000, exposure=30.0)]
    assert len(zones.build_zones(cands, cluster_dist=50.0)) == 2


def test_nearby_pairs_merge_with_height_range() -> None:
    # rows 30 m apart: anchors fall within cluster_dist=50 -> one zone
    cands = [make_pair(0, 80, 0, exposure=60.0),
             make_pair(0, 80, 30, exposure=25.0)]
    [z] = zones.build_zones(cands, cluster_dist=50.0)
    assert z.n_anchors == 4
    assert z.n_pairs == 2
    assert z.height_min == 25.0
    assert z.height_max == 60.0


def test_zones_sorted_by_height_max_desc() -> None:
    cands = [make_pair(0, 80, 0, exposure=20.0),
             make_pair(0, 80, 10000, exposure=90.0)]
    zs = zones.build_zones(cands, cluster_dist=50.0)
    assert [z.height_max for z in zs] == [90.0, 20.0]


def test_shared_anchor_merges_pairs() -> None:
    # two pairs sharing anchor a -> one component even with tiny cluster_dist
    a = Anchor(x=0.0, y=0.0, elev=100.0, sectors=((80, 100, 60),))
    b = Anchor(x=80.0, y=0.0, elev=100.0, sectors=((260, 280, 60),))
    c = Anchor(x=0.0, y=80.0, elev=100.0, sectors=((170, 190, 60),))
    cands = [
        Candidate(a=a, b=b, length=80.0, exposure=40.0, height_diff=0.0),
        Candidate(a=a, b=c, length=80.0, exposure=70.0, height_diff=0.0),
    ]
    [z] = zones.build_zones(cands, cluster_dist=1.0)
    assert z.n_anchors == 3
    assert z.n_pairs == 2
    assert (z.height_min, z.height_max) == (40.0, 70.0)


def test_to_geojson_polygons_with_properties() -> None:
    from highliner.router.serializers import zones_to_geojson
    zs = zones.build_zones([make_pair(420000, 420080, 4600000, exposure=60.0)])
    fc = zones_to_geojson(zs)
    assert fc["type"] == "FeatureCollection"
    [f] = fc["features"]
    assert f["geometry"]["type"] == "Polygon"
    ring = f["geometry"]["coordinates"][0]
    assert len(ring) >= 4 and ring[0] == ring[-1]   # closed ring
    # UTM 420000,4600000 is ~lon 2.0, lat 41.5 in Catalonia
    lon, lat = ring[0]
    assert 1.5 < lon < 2.5 and 41.0 < lat < 42.0
    assert f["properties"] == {
        "height_min": 60.0, "height_max": 60.0,
        "n_anchors": 2, "n_pairs": 1,
    }
