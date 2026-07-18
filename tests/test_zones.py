from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate

from highliner.server.services import zones


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
    assert z.length_min == z.length_max == 80.0
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
             make_pair(0, 45, 30, exposure=25.0)]
    [z] = zones.build_zones(cands, cluster_dist=50.0)
    assert z.n_anchors == 4
    assert z.n_pairs == 2
    assert z.height_min == 25.0
    assert z.height_max == 60.0
    assert z.length_min == 45.0
    assert z.length_max == 80.0


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
    from highliner.server.router.serializers import zones_to_geojson
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
        "length_min": 80.0, "length_max": 80.0,
        "n_anchors": 2, "n_pairs": 1,
    }


def test_reproject_candidates_same_crs_is_noop() -> None:
    inp = [make_pair(0, 80, 0, exposure=60.0)]
    out = zones.reproject_candidates(inp, "EPSG:25831", "EPSG:25831")
    assert out is inp


def test_reproject_candidates_moves_coords_keeps_metrics() -> None:
    from highliner.core import geo

    ax, ay = geo.from_lonlat_crs(0.72, 42.05, "EPSG:25831")
    a = Anchor(x=ax, y=ay, elev=120.0, sectors=((80.0, 100.0, 60.0),))
    b = Anchor(x=ax + 80, y=ay, elev=118.0, sectors=((260.0, 280.0, 60.0),))
    c = Candidate(a=a, b=b, length=80.0, exposure=75.0, height_diff=2.0)

    [out] = zones.reproject_candidates([c], "EPSG:25831", "EPSG:25830")
    # metric fields untouched
    assert out.length == 80.0 and out.exposure == 75.0 and out.height_diff == 2.0
    assert out.a.elev == 120.0 and out.a.sectors == a.sectors
    # coordinates actually moved
    assert abs(out.a.x - ax) > 1.0
    # round-trip back is ~identity
    [back] = zones.reproject_candidates([out], "EPSG:25830", "EPSG:25831")
    assert abs(back.a.x - ax) < 1e-3 and abs(back.a.y - ay) < 1e-3


def test_dedup_collapses_offset_duplicate() -> None:
    # Same line, re-extracted a few meters off (within the grid), same
    # length and bearing -> one survivor.
    c1 = make_pair(0, 80, 0, exposure=60.0)   # midpoint (40, 0), len 80, brg 90
    c2 = make_pair(3, 83, 4, exposure=61.0)   # midpoint (43, 4), len 80, brg 90
    out = zones.dedup_candidates([c1, c2])
    assert len(out) == 1


def test_dedup_keeps_distant_lines() -> None:
    c1 = make_pair(0, 80, 0, exposure=60.0)     # midpoint (40, 0)
    c2 = make_pair(0, 80, 500, exposure=60.0)   # midpoint (40, 500)
    assert len(zones.dedup_candidates([c1, c2])) == 2


def test_dedup_keeps_crossing_lines_same_midpoint() -> None:
    # Same midpoint and length, perpendicular bearings -> both survive.
    horiz = Candidate(
        a=Anchor(x=-40, y=0, elev=100.0, sectors=((80.0, 100.0, 60.0),)),
        b=Anchor(x=40, y=0, elev=100.0, sectors=((260.0, 280.0, 60.0),)),
        length=80.0, exposure=60.0, height_diff=0.0)
    vert = Candidate(
        a=Anchor(x=0, y=-40, elev=100.0, sectors=((170.0, 190.0, 60.0),)),
        b=Anchor(x=0, y=40, elev=100.0, sectors=((350.0, 10.0, 60.0),)),
        length=80.0, exposure=60.0, height_diff=0.0)
    assert len(zones.dedup_candidates([horiz, vert])) == 2
