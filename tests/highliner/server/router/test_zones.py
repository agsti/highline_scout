from pathlib import Path

from fastapi.testclient import TestClient

from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.server.app import create_app
from tests.helpers import Pair as _Pair
from tests.helpers import facing_pair as _facing_pair
from tests.helpers import gap_region as _gap_region
from tests.helpers import to_utm
from tests.helpers import write_region as _write_region


def test_zones_endpoint(tmp_path: Path) -> None:
    _gap_region(tmp_path)
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    assert "test" in [r["name"] for r in client.get("/regions").json()["regions"]]

    r = client.get("/zones", params={
        "region": "test",
        "bbox": "0,0,300,300",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    f = fc["features"][0]
    assert f["geometry"]["type"] == "Polygon"
    p = f["properties"]
    assert p["n_anchors"] == 2 and p["n_pairs"] == 1
    assert p["height_min"] == p["height_max"] == 80.0  # plateau 100, gap 20


def test_zones_slider_filters_out_pair(tmp_path: Path) -> None:
    _gap_region(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={"region": "test", "bbox": "0,0,300,300",
                                     "min_exposure": 90})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_zones_bbox_lonlat(tmp_path: Path) -> None:
    # Place the region's anchors at real Catalan UTM coords and query with a
    # lon/lat bbox that covers them, exercising the WGS84 -> UTM conversion.
    cx, cy = to_utm(1.83, 41.59)  # near Montserrat
    a = Anchor(x=cx - 40, y=cy, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    b = Anchor(x=cx + 40, y=cy, elev=100.0, sectors=((260.0, 280.0, 60.0),))
    c = Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)
    _write_region(tmp_path, "geo",
                  (cx - 200.0, cy - 200.0, cx + 200.0, cy + 200.0), [a, b], [c])

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "region": "geo",
        "bbox_lonlat": "1.82,41.58,1.84,41.60",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    assert len(r.json()["features"]) == 1

    # /regions reports each region's lon/lat extent so the UI can fly to it.
    entry = next(e for e in client.get("/regions").json()["regions"]
                 if e["name"] == "geo")
    w, s, e_, n = entry["bounds_lonlat"]
    assert w < e_ and s < n
    assert w <= 1.83 <= e_ and s <= 41.59 <= n  # the region's own extent


def test_zones_bbox_lonlat_region_crs(tmp_path: Path) -> None:
    from highliner.core import geo
    cx, cy = geo.from_lonlat_crs(-16.25, 28.45, "EPSG:4083")
    a = Anchor(x=cx - 40, y=cy, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    b = Anchor(x=cx + 40, y=cy, elev=100.0, sectors=((260.0, 280.0, 60.0),))
    c = Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)
    _write_region(tmp_path, "canarias", (cx - 200.0, cy - 200.0,
                  cx + 200.0, cy + 200.0), [a, b], [c], crs="EPSG:4083")

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "region": "canarias",
        "bbox_lonlat": "-16.26,28.44,-16.24,28.46",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    assert len(r.json()["features"]) == 1


def test_zones_viewport_scoped_to_country(tmp_path: Path) -> None:
    # Two regions inside one viewport but in different country partitions; a
    # region-less /zones request only serves the requested country's regions.
    cx1, cy1, a1, b1, c1 = _facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx1 - 200, cy1 - 200, cx1 + 200, cy1 + 200),
                  [a1, b1], [c1])                              # spain (default)
    cx2, cy2, a2, b2, c2 = _facing_pair(1.95, 41.60)
    _write_region(tmp_path, "two", (cx2 - 200, cy2 - 200, cx2 + 200, cy2 + 200),
                  [a2, b2], [c2], country="france")
    client = TestClient(create_app(data_dir=tmp_path))
    params = {"bbox_lonlat": "1.80,41.55,2.00,41.65",
              "max_len": 120, "min_exposure": 50, "max_dh": 5}

    assert len(client.get("/zones", params=params).json()["features"]) == 1
    france = client.get("/zones", params={**params, "country": "france"})
    assert len(france.json()["features"]) == 1


def test_zones_merges_two_regions_by_viewport(tmp_path: Path) -> None:
    # Two regions with real UTM coords whose lon/lat extents both fall inside one
    # wide viewport; a region-less /zones request must return zones from both.
    cx1, cy1, a1, b1, c1 = _facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx1 - 200, cy1 - 200, cx1 + 200, cy1 + 200),
                  [a1, b1], [c1])
    cx2, cy2, a2, b2, c2 = _facing_pair(1.95, 41.60)
    _write_region(tmp_path, "two", (cx2 - 200, cy2 - 200, cx2 + 200, cy2 + 200),
                  [a2, b2], [c2])

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "bbox_lonlat": "1.80,41.55,2.00,41.65",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    assert len(r.json()["features"]) == 2


def test_zones_region_omitted_no_overlap_is_empty(tmp_path: Path) -> None:
    _gap_region(tmp_path, "one")  # tiny region near (0,0) UTM, not real lon/lat
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={"bbox_lonlat": "1.80,41.55,2.00,41.65"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_zones_merges_cross_crs_seam_into_one_zone(tmp_path: Path) -> None:
    # A pair in a 25830 region and a nearby pair in a 25831 region, ~33 m apart,
    # both inside one viewport straddling the Aragon/Catalonia seam. The old
    # per-region loop returned two fragments; the merge returns one zone.
    from highliner.core import geo

    def pair_in(crs: str, dlat: float) -> _Pair:
        cx, cy = geo.from_lonlat_crs(0.72, 42.05 + dlat, crs)
        a = Anchor(x=cx - 40, y=cy, elev=100.0, sectors=((80.0, 100.0, 60.0),))
        b = Anchor(x=cx + 40, y=cy, elev=100.0, sectors=((260.0, 280.0, 60.0),))
        c = Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)
        return cx, cy, a, b, c

    cxA, cyA, aA, bA, cA = pair_in("EPSG:25830", 0.0)
    _write_region(tmp_path, "aragon", (cxA - 200, cyA - 200, cxA + 200, cyA + 200),
                  [aA, bA], [cA], crs="EPSG:25830")
    cxB, cyB, aB, bB, cB = pair_in("EPSG:25831", 0.0003)  # ~33 m north
    _write_region(tmp_path, "catalonia",
                  (cxB - 200, cyB - 200, cxB + 200, cyB + 200),
                  [aB, bB], [cB])  # no crs -> defaults to 25831

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "bbox_lonlat": "0.70,42.03,0.74,42.07",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    fc = r.json()
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert props["n_pairs"] == 2 and props["n_anchors"] == 4


def test_zones_cross_crs_duplicate_collapses_to_one_pair(tmp_path: Path) -> None:
    # The SAME physical line, written into a 25830 region and a 25831 region
    # (no offset between them). A plain cluster-merge would keep both copies
    # as two distinct pairs (n_pairs == 2); only the reproject -> dedup path
    # collapses them into a single surviving pair. n_pairs == 1 is therefore
    # proof the dedup step ran, not just the union-find merge.
    import math

    from highliner.core import geo

    # lon0/lat0 chosen (and verified) so the reprojected midpoint lands ~1 m
    # from a 15 m grid-cell center (round(mx/15) boundaries sit at the
    # cell's +-7.5 m edges) -- comfortably mid-cell, not boundary-sensitive.
    lon0, lat0 = 0.70, 42.00
    dlon = 80.0 / (111320.0 * math.cos(math.radians(lat0)))  # ~80 m east
    lon1 = lon0 + dlon

    def line_in(crs: str) -> tuple[Anchor, Anchor, Candidate]:
        ax, ay = geo.from_lonlat_crs(lon0, lat0, crs)
        bx, by = geo.from_lonlat_crs(lon1, lat0, crs)
        a = Anchor(x=ax, y=ay, elev=100.0, sectors=((80.0, 100.0, 60.0),))
        b = Anchor(x=bx, y=by, elev=100.0, sectors=((260.0, 280.0, 60.0),))
        c = Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)
        return a, b, c

    aA, bA, cA = line_in("EPSG:25830")
    _write_region(tmp_path, "aragon",
                  (aA.x - 200, aA.y - 200, bA.x + 200, bA.y + 200),
                  [aA, bA], [cA], crs="EPSG:25830")
    aB, bB, cB = line_in("EPSG:25831")
    _write_region(tmp_path, "catalonia",
                  (aB.x - 200, aB.y - 200, bB.x + 200, bB.y + 200),
                  [aB, bB], [cB])  # no crs -> defaults to 25831

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "bbox_lonlat": "0.68,41.99,0.72,42.01",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    fc = r.json()
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert props["n_pairs"] == 1 and props["n_anchors"] == 2
