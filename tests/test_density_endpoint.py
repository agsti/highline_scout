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
        json.dumps([{"x": tx, "y": ty, "n": 3, "max_exp": 85.0}]))
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


def test_density_bbox_excludes_far_cell(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "3.0,42.0,3.1,42.1"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_density_clamps_zoom(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12)  # only z12 exists
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 20, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 200  # z clamped to 12
    assert len(r.json()["features"]) == 1


def test_density_404_without_dir(tmp_path: Path) -> None:
    (tmp_path / "catalonia").mkdir(parents=True)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 404
