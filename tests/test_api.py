import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from highliner.etls.chunk.anchors import save_anchors
from highliner.etls.chunk.candidates import save_candidates
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.server.app import create_app

from highliner.core import config
from tests.helpers import to_utm

# (centre_x, centre_y, anchor_a, anchor_b, candidate) for one facing pair.
_Pair = tuple[float, float, Anchor, Anchor, Candidate]


def _write_region(data_dir: Path, region: str,  # noqa: PLR0913
                  bbox: tuple[float, float, float, float],
                  anchors: list[Anchor], candidates: list[Candidate],
                  chunk_m: float = 10000.0,
                  crs: str | None = None,
                  country: str = "spain") -> None:
    """Write a minimal one-chunk region in the layout the API expects."""
    rdir = data_dir / country / region
    (rdir / "anchors").mkdir(parents=True)
    (rdir / "pairs").mkdir(parents=True)
    grid = {"bbox": list(bbox), "chunk_m": chunk_m}
    if crs is not None:
        grid["crs"] = crs
    (rdir / "grid.json").write_text(json.dumps(grid))
    save_anchors(anchors, rdir / "anchors" / "p_0_0.parquet")
    save_candidates(candidates, rdir / "pairs" / "q_0_0.parquet")


def _gap_region(data_dir: Path, region: str = "test") -> None:
    """Two facing anchors 80 m apart across an 80 m-deep gap (plateau 100, gap 20)."""
    a = Anchor(x=60.0, y=100.0, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    b = Anchor(x=140.0, y=100.0, elev=100.0, sectors=((260.0, 280.0, 60.0),))
    c = Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)
    _write_region(data_dir, region, (0.0, 0.0, 300.0, 300.0), [a, b], [c])


def _facing_pair(lon: float, lat: float) -> _Pair:
    """Two facing anchors 80 m apart, centred on the UTM projection of (lon, lat)."""
    cx, cy = to_utm(lon, lat)
    a = Anchor(x=cx - 40, y=cy, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    b = Anchor(x=cx + 40, y=cy, elev=100.0, sectors=((260.0, 280.0, 60.0),))
    c = Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)
    return cx, cy, a, b, c


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


def test_candidates_route_removed(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/candidates", params={"region": "test", "bbox": "0,0,300,300"})
    assert r.status_code == 404


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


def test_anchors_endpoint(tmp_path: Path) -> None:
    _gap_region(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"region": "test", "bbox": "0,0,300,300"})
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2
    assert fc["features"][0]["geometry"]["type"] == "Point"
    assert fc["features"][0]["properties"]["sectors"]


def test_anchors_filters_out_of_view(tmp_path: Path) -> None:
    _gap_region(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    # bbox covers anchor a (x=60) but not b (x=140)
    r = client.get("/anchors", params={"region": "test", "bbox": "0,0,100,300"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 1


def test_anchors_cap_413(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _gap_region(tmp_path)
    monkeypatch.setattr(config, "MAX_ANCHORS_IN_VIEW", 1)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"region": "test", "bbox": "0,0,300,300"})
    assert r.status_code == 413


def test_regions_lists_region(tmp_path: Path) -> None:
    _gap_region(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    found = [r for r in client.get("/regions").json()["regions"] if r["name"] == "test"]
    assert len(found) == 1
    b = found[0]["bounds_lonlat"]
    assert b is not None and len(b) == 4
    assert b[0] < b[2] and b[1] < b[3]


def test_regions_exposes_country_and_filters(tmp_path: Path) -> None:
    cx1, cy1, a1, b1, c1 = _facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx1 - 200, cy1 - 200, cx1 + 200, cy1 + 200),
                  [a1, b1], [c1])                              # spain (default)
    cx2, cy2, a2, b2, c2 = _facing_pair(1.95, 41.60)
    _write_region(tmp_path, "two", (cx2 - 200, cy2 - 200, cx2 + 200, cy2 + 200),
                  [a2, b2], [c2], country="france")
    client = TestClient(create_app(data_dir=tmp_path))

    default = client.get("/regions").json()["regions"]   # default country: spain
    assert [r["name"] for r in default] == ["one"]
    assert default[0]["country"] == "spain"

    fr = client.get("/regions", params={"country": "france"}).json()["regions"]
    assert [(r["name"], r["country"]) for r in fr] == [("two", "france")]


def test_countries_lists_precomputed_country_coverage(tmp_path: Path) -> None:
    cx1, cy1, a1, b1, c1 = _facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx1 - 200, cy1 - 200, cx1 + 200, cy1 + 200),
                  [a1, b1], [c1])
    cx2, cy2, a2, b2, c2 = _facing_pair(1.95, 41.60)
    _write_region(tmp_path, "two", (cx2 - 200, cy2 - 200, cx2 + 200, cy2 + 200),
                  [a2, b2], [c2], country="france")
    client = TestClient(create_app(data_dir=tmp_path))

    countries = client.get("/countries").json()["countries"]

    assert [country["id"] for country in countries] == ["france", "spain"]
    assert all(len(country["bounds_lonlat"]) == 4 for country in countries)
    assert all("center_lonlat" not in country for country in countries)


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


def _write_restriction_layer(
        data_dir: Path, layer_id: str, name: str,
        lonlat_box: tuple[float, float, float, float],
        country: str = "spain") -> None:
    """Write a one-polygon restriction layer (lon/lat) to data_dir."""
    import geopandas as gpd
    from shapely.geometry import box
    rdir = data_dir / country / "restrictions"
    rdir.mkdir(parents=True, exist_ok=True)
    w, s, e, n = lonlat_box
    gdf = gpd.GeoDataFrame({"name": [name]}, geometry=[box(w, s, e, n)],
                           crs="EPSG:4326")
    gdf.to_parquet(rdir / f"{layer_id}.parquet")


def test_restriction_layers_are_scoped_to_country(tmp_path: Path) -> None:
    _write_restriction_layer(tmp_path, "zepa", "Montserrat",
                             (1.80, 41.55, 1.85, 41.62), country="spain")
    _write_restriction_layer(tmp_path, "zps", "Dolomites",
                             (11.80, 46.45, 11.85, 46.52), country="italy")
    client = TestClient(create_app(data_dir=tmp_path))

    assert [layer["id"] for layer in client.get(
        "/restrictions/layers", params={"country": "spain"}
    ).json()["layers"]] == ["zepa"]
    assert [layer["id"] for layer in client.get(
        "/restrictions/layers", params={"country": "italy"}
    ).json()["layers"]] == ["zps"]
    assert client.get(
        "/restrictions/layers", params={"country": "france"}
    ).json()["layers"] == []


def test_restrictions_in_view(tmp_path: Path) -> None:
    _write_restriction_layer(tmp_path, "zepa", "Montserrat",
                             (1.80, 41.55, 1.85, 41.62))
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/restrictions", params={
        "bbox_lonlat": "1.78,41.54,1.90,41.66", "layers": "zepa"})
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert props["layer"] == "zepa"
    assert props["name"] == "Montserrat"


def test_restrictions_filters_out_of_view(tmp_path: Path) -> None:
    _write_restriction_layer(tmp_path, "zepa", "Montserrat",
                             (1.80, 41.55, 1.85, 41.62))
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/restrictions", params={
        "bbox_lonlat": "2.50,42.00,2.60,42.10", "layers": "zepa"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_restrictions_missing_data_is_empty(tmp_path: Path) -> None:
    # No restrictions downloaded yet -> endpoint still works, returns nothing.
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/restrictions", params={"bbox_lonlat": "1.0,41.0,2.0,42.0"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_restrictions_scoped_to_country(tmp_path: Path) -> None:
    # A layer stored only under the france partition is invisible to the default
    # (spain) request, and served when france is requested.
    _write_restriction_layer(tmp_path, "zepa", "Écrins",
                             (1.80, 41.55, 1.85, 41.62), country="france")
    client = TestClient(create_app(data_dir=tmp_path))
    view = {"bbox_lonlat": "1.78,41.54,1.90,41.66", "layers": "zepa"}

    assert client.get("/restrictions", params=view).json()["features"] == []
    got = client.get("/restrictions", params={**view, "country": "france"})
    assert len(got.json()["features"]) == 1
    assert client.get("/restrictions", params={
        **view, "country": "france", "layers": "zps",
    }).json()["features"] == []


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


def test_anchors_merges_two_regions(tmp_path: Path) -> None:
    cx1, cy1, a1, b1, c1 = _facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx1 - 200, cy1 - 200, cx1 + 200, cy1 + 200),
                  [a1, b1], [c1])
    cx2, cy2, a2, b2, c2 = _facing_pair(1.95, 41.60)
    _write_region(tmp_path, "two", (cx2 - 200, cy2 - 200, cx2 + 200, cy2 + 200),
                  [a2, b2], [c2])

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"bbox_lonlat": "1.80,41.55,2.00,41.65"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 4  # 2 anchors per region


def test_anchors_merged_cap_413(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cx1, cy1, a1, b1, c1 = _facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx1 - 200, cy1 - 200, cx1 + 200, cy1 + 200),
                  [a1, b1], [c1])
    cx2, cy2, a2, b2, c2 = _facing_pair(1.95, 41.60)
    _write_region(tmp_path, "two", (cx2 - 200, cy2 - 200, cx2 + 200, cy2 + 200),
                  [a2, b2], [c2])

    # 2 anchors per region overlap the viewport; a cap of 3 must trip on the total.
    monkeypatch.setattr(config, "MAX_ANCHORS_IN_VIEW", 3)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"bbox_lonlat": "1.80,41.55,2.00,41.65"})
    assert r.status_code == 413


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


def test_app_installs_slow_request_middleware() -> None:
    from typing import cast

    from highliner.core.telemetry import SlowRequestMiddleware

    app = create_app()

    # Starlette types .cls as a middleware factory, so compare through object.
    installed = [cast(object, m.cls) for m in app.user_middleware]
    assert SlowRequestMiddleware in installed


def test_app_compresses_eligible_responses() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.json()["openapi"] == "3.1.0"


def test_app_sends_nothing_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default (unconfigured) app must not attempt any telemetry IO.

    Threshold is forced to 0 so every request crosses it — if the disabled-state
    guard were missing, this would call into an unarmed PostHog client.
    """
    import posthog

    monkeypatch.setattr(config.settings, "slow_request_ms", 0.0)
    calls: list[object] = []
    monkeypatch.setattr(posthog, "capture", lambda **kwargs: calls.append(kwargs))

    client = TestClient(create_app(tmp_path))
    client.get("/regions")

    assert calls == []
