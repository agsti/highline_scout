from pathlib import Path
from typing import Callable
import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from highliner.models.anchor import Anchor
from highliner.repositories.anchors import save_anchors
from highliner.app import create_app
from highliner.core import config


def _setup_region(data_dir: Path) -> None:
    region = data_dir / "test"
    region.mkdir(parents=True)
    # DTM: plateau 100 with a gap (20) between x cols 31..69 (2m px from origin)
    data = np.full((101, 101), 100.0, dtype="float32")
    data[:, 31:70] = 20.0
    transform = from_origin(0, 202, 2.0, 2.0)
    with rasterio.open(region / "mosaic.tif", "w", driver="GTiff",
                       height=101, width=101, count=1, dtype="float32",
                       crs="EPSG:25831", transform=transform) as ds:
        ds.write(data, 1)
    # two facing anchors across the gap (UTM coords)
    a = Anchor(x=60.0, y=100.0, elev=100.0, sectors=((80, 100, 60),))
    b = Anchor(x=140.0, y=100.0, elev=100.0, sectors=((260, 280, 60),))
    save_anchors([a, b], region / "anchors.parquet")


def test_zones_endpoint(tmp_path: Path) -> None:
    _setup_region(tmp_path)
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


def test_candidates_route_removed(tmp_path: Path) -> None:
    _setup_region(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/candidates", params={"region": "test", "bbox": "0,0,300,300"})
    assert r.status_code == 404


def test_zones_bbox_lonlat(tmp_path: Path) -> None:
    # Place the region's anchors at real Catalan UTM coords and query with a
    # lon/lat bbox that covers them, exercising the WGS84 -> UTM conversion.
    from highliner.core import geo
    region = tmp_path / "geo"
    region.mkdir(parents=True)
    cx, cy = geo.to_utm(1.83, 41.59)  # near Montserrat
    data = np.full((101, 101), 100.0, dtype="float32")
    data[:, 31:70] = 20.0
    transform = from_origin(cx - 100, cy + 102, 2.0, 2.0)
    with rasterio.open(region / "mosaic.tif", "w", driver="GTiff",
                       height=101, width=101, count=1, dtype="float32",
                       crs="EPSG:25831", transform=transform) as ds:
        ds.write(data, 1)
    a = Anchor(x=cx - 40, y=cy, elev=100.0, sectors=((80, 100, 60),))
    b = Anchor(x=cx + 40, y=cy, elev=100.0, sectors=((260, 280, 60),))
    save_anchors([a, b], region / "anchors.parquet")

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
    assert w <= 1.83 <= e_ and s <= 41.59 <= n  # the mosaic's own extent


def test_analyze_enqueues_and_completes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.tasks import analyze as tasks
    from highliner.services import pipeline
    tasks.huey.immediate = True
    try:
        def fake_analyze(bbox: object, region: str, data_dir: str | Path, report: Callable[[str, int, int], None] | None = None) -> int:
            from pathlib import Path
            d = Path(data_dir) / region
            d.mkdir(parents=True, exist_ok=True)
            save_anchors([], d / "anchors.parquet")
            with rasterio.open(d / "mosaic.tif", "w", driver="GTiff", height=4,
                               width=4, count=1, dtype="float32",
                               crs="EPSG:25831",
                               transform=from_origin(0, 8, 2.0, 2.0)) as ds:
                ds.write(np.zeros((4, 4), "float32"), 1)
            return 0
        monkeypatch.setattr(pipeline, "analyze_area", fake_analyze)

        client = TestClient(create_app(data_dir=tmp_path))
        r = client.post("/analyze", json={
            "name": "Test Area", "bbox_lonlat": "2.80,41.96,2.81,41.97"})
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        job = client.get(f"/jobs/{job_id}").json()
        assert job["status"] == "done"
        assert client.get("/jobs").json()["jobs"]  # non-empty list
    finally:
        tasks.huey.immediate = False


def test_analyze_rejects_too_large(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    # ~0.5 x 0.5 degree -> tens of thousands of tiles, over the cap
    r = client.post("/analyze", json={
        "name": "Huge", "bbox_lonlat": "2.0,41.5,2.5,42.0"})
    assert r.status_code == 400


def test_jobs_unknown_id_404(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.get("/jobs/nope").status_code == 404


def test_consumer_starts_when_not_immediate(tmp_path: Path) -> None:
    from highliner.tasks import analyze as tasks
    assert tasks.huey.immediate is False  # default
    app = create_app(data_dir=tmp_path)
    with TestClient(app):  # triggers startup
        assert getattr(app.state, "huey_consumer", None) is not None
    # after context exit (shutdown) the consumer is stopped
    assert app.state.huey_consumer_stopped is True


def test_anchors_endpoint(tmp_path: Path) -> None:
    _setup_region(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"region": "test", "bbox": "0,0,300,300"})
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2
    assert fc["features"][0]["geometry"]["type"] == "Point"
    assert fc["features"][0]["properties"]["sectors"]


def test_anchors_filters_out_of_view(tmp_path: Path) -> None:
    _setup_region(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    # bbox covers anchor a (x=60) but not b (x=140)
    r = client.get("/anchors", params={"region": "test", "bbox": "0,0,100,300"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 1


def test_anchors_cap_413(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_region(tmp_path)
    monkeypatch.setattr(config, "MAX_ANCHORS_IN_VIEW", 1)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"region": "test", "bbox": "0,0,300,300"})
    assert r.status_code == 413


def _write_restriction_layer(data_dir: Path, layer_id: str, name: str, lonlat_box: tuple[float, float, float, float]) -> None:
    """Write a one-polygon restriction layer (lon/lat) to data_dir."""
    import geopandas as gpd
    from shapely.geometry import box
    rdir = data_dir / "restrictions"
    rdir.mkdir(parents=True, exist_ok=True)
    w, s, e, n = lonlat_box
    gdf = gpd.GeoDataFrame({"name": [name]}, geometry=[box(w, s, e, n)],
                           crs="EPSG:4326")
    gdf.to_parquet(rdir / f"{layer_id}.parquet")


def test_restriction_layers_registry(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/restrictions/layers")
    assert r.status_code == 200
    layers = r.json()["layers"]
    ids = {row["id"] for row in layers}
    assert {"pein", "parcs", "fauna"} <= ids
    assert "zec" not in ids and "zepa" not in ids  # dropped: overlap PEIN
    pein = next(row for row in layers if row["id"] == "pein")
    assert pein["label"] and pein["color"].startswith("#")
    assert all(row["tooltip"].strip() for row in layers)
    # every layer emphasizes its highliner-relevant clause; the highlight must
    # be a verbatim substring of the tooltip so the frontend can locate it.
    for row in layers:
        assert row["highlight"] and row["highlight"] in row["tooltip"]


def test_restrictions_in_view(tmp_path: Path) -> None:
    _write_restriction_layer(tmp_path, "pein", "Montserrat",
                             (1.80, 41.55, 1.85, 41.62))
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/restrictions", params={
        "bbox_lonlat": "1.78,41.54,1.90,41.66", "layers": "pein"})
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert props["layer"] == "pein"
    assert props["name"] == "Montserrat"


def test_restrictions_filters_out_of_view(tmp_path: Path) -> None:
    _write_restriction_layer(tmp_path, "pein", "Montserrat",
                             (1.80, 41.55, 1.85, 41.62))
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/restrictions", params={
        "bbox_lonlat": "2.50,42.00,2.60,42.10", "layers": "pein"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_restrictions_missing_data_is_empty(tmp_path: Path) -> None:
    # No restrictions downloaded yet -> endpoint still works, returns nothing.
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/restrictions", params={"bbox_lonlat": "1.0,41.0,2.0,42.0"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def _setup_catalonia(data_dir: Path) -> None:
    import json
    from highliner.models.candidate import Candidate
    from highliner.repositories.candidates import save_candidates
    region = data_dir / "catalonia"
    (region / "anchors").mkdir(parents=True)
    (region / "pairs").mkdir(parents=True)
    (region / "grid.json").write_text(json.dumps(
        {"bbox": [0.0, 0.0, 10000.0, 10000.0], "chunk_m": 10000.0}))
    a = Anchor(x=60.0, y=100.0, elev=100.0, sectors=())
    b = Anchor(x=140.0, y=100.0, elev=100.0, sectors=())
    save_anchors([a, b], region / "anchors" / "p_0_0.parquet")
    save_candidates([Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)],
                    region / "pairs" / "q_0_0.parquet")


def test_zones_endpoint_catalonia_layout(tmp_path: Path) -> None:
    _setup_catalonia(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "region": "catalonia", "bbox": "0,0,300,300",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    fc = r.json()
    assert len(fc["features"]) == 1
    p = fc["features"][0]["properties"]
    assert p["n_pairs"] == 1 and p["height_min"] == p["height_max"] == 80.0


def test_zones_slider_filters_out_pair(tmp_path: Path) -> None:
    _setup_catalonia(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "region": "catalonia", "bbox": "0,0,300,300", "min_exposure": 90})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_anchors_endpoint_catalonia_layout(tmp_path: Path) -> None:
    _setup_catalonia(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"region": "catalonia", "bbox": "0,0,300,300"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 2
