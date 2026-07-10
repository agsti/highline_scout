import json
from pathlib import Path

from fastapi.testclient import TestClient

from highliner.app import create_app
from highliner.core import tiles


def _write_density(data_dir: Path, region: str, z: int) -> tuple[int, int]:
    """Write a one-cell z-layer near Montserrat; return its (xtile, ytile)."""
    tx, ty = tiles.lonlat_to_tile(1.83, 41.59, z)
    ddir = data_dir / region / "density"
    ddir.mkdir(parents=True)
    (ddir / f"z{z}.json").write_text(
        json.dumps([{"x": tx, "y": ty, "n": 3, "max_exp": 85.0,
                     "min_len": 40.0, "max_len": 120.0}]))
    return tx, ty


def test_density_returns_clipped_cell(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    f = fc["features"][0]
    assert f["geometry"]["type"] == "Polygon"
    assert f["properties"]["n_pairs"] == 3
    assert f["properties"]["max_exposure"] == 85.0
    assert f["properties"]["length_min"] == 40.0
    assert f["properties"]["length_max"] == 120.0


def test_density_legacy_cell_without_length(tmp_path: Path) -> None:
    # Cells precomputed before the length fields existed must not 500.
    tx, ty = tiles.lonlat_to_tile(1.83, 41.59, 12)
    ddir = tmp_path / "catalonia" / "density"
    ddir.mkdir(parents=True)
    (ddir / "z12.json").write_text(
        json.dumps([{"x": tx, "y": ty, "n": 3, "max_exp": 85.0}]))
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 200
    props = r.json()["features"][0]["properties"]
    assert props["length_min"] is None
    assert props["length_max"] is None


def test_density_bbox_excludes_far_cell(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "3.0,42.0,3.1,42.1"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_density_clamps_zoom(tmp_path: Path) -> None:
    from highliner.core import config
    zmax = config.DENSITY_ZOOM_LEVELS.stop - 1  # deepest precomputed layer
    _write_density(tmp_path, "catalonia", zmax)  # only the deepest layer exists
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 99, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 200  # z clamped into the precomputed range
    assert len(r.json()["features"]) == 1


def test_density_404_without_dir(tmp_path: Path) -> None:
    (tmp_path / "catalonia").mkdir(parents=True)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 404


def _write_grid(data_dir: Path, region: str,
                bbox: tuple[float, float, float, float]) -> None:
    (data_dir / region).mkdir(parents=True, exist_ok=True)
    (data_dir / region / "grid.json").write_text(
        json.dumps({"bbox": list(bbox), "chunk_m": 10000.0}))


def test_density_merges_regions_when_region_omitted(tmp_path: Path) -> None:
    from highliner.core import geo
    # Two indexed regions near Montserrat, each with one density cell at z12.
    cx, cy = geo.to_utm(1.83, 41.59)
    _write_grid(tmp_path, "one", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_grid(tmp_path, "two", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_density(tmp_path, "one", 12)
    _write_density(tmp_path, "two", 12)

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 2
