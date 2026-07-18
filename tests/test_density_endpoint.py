import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from highliner.core import tiles
from highliner.server.app import create_app
from tests.helpers import to_utm

# A histogram row of (length bucket, exposure bucket, mask, count). Bucket 10 is
# 100-110 m and exposure bucket 3 is 30-40 m, so these rows pass the defaults
# (min_len 20, max_len 150, min_exposure 30).
DEFAULT_HIST = [(10, 3, 0, 3)]


def _write_density(data_dir: Path, region: str, z: int,
                   hist: list[tuple[int, int, int, int]] = DEFAULT_HIST,
                   ) -> tuple[int, int]:
    """Write a one-cell z-layer near Montserrat; return its (xtile, ytile)."""
    tx, ty = tiles.lonlat_to_tile(1.83, 41.59, z)
    cx, cy = to_utm(1.83, 41.59)
    _write_grid(data_dir, region, (cx - 500, cy - 500, cx + 500, cy + 500))
    density_dir = data_dir / "spain" / region / "density"
    density_dir.mkdir(parents=True, exist_ok=True)
    np.savez(
        density_dir / f"z{z}.npz",
        cx=np.array([tx], dtype=np.int32),
        cy=np.array([ty], dtype=np.int32),
        n=np.array([sum(row[3] for row in hist)], dtype=np.int32),
        max_exp=np.array([85.0], dtype=np.float32),
        min_len=np.array([40.0], dtype=np.float32),
        max_len=np.array([120.0], dtype=np.float32),
        off=np.array([0, len(hist)], dtype=np.int64),
        hl=np.array([row[0] for row in hist], dtype=np.int16),
        he=np.array([row[1] for row in hist], dtype=np.int16),
        hm=np.array([row[2] for row in hist], dtype=np.int8),
        hc=np.array([row[3] for row in hist], dtype=np.int32),
    )
    return tx, ty


def test_density_returns_clipped_cell(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert response.status_code == 200
    collection = response.json()
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 1
    feature = collection["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["properties"]["n_pairs"] == 3
    assert feature["properties"]["max_exposure"] == 85.0
    assert feature["properties"]["length_min"] == 100.0
    assert feature["properties"]["length_max"] == 110.0


def test_density_bbox_excludes_far_cell(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "3.0,42.0,3.1,42.1"})
    assert response.status_code == 200
    assert response.json()["features"] == []


def test_density_clamps_zoom(tmp_path: Path) -> None:
    from highliner.core import config

    zmax = config.DENSITY_ZOOM_LEVELS.stop - 1
    _write_density(tmp_path, "catalonia", zmax)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.get("/density", params={
        "region": "catalonia", "z": 99, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert response.status_code == 200
    assert len(response.json()["features"]) == 1


def test_density_404_without_dir(tmp_path: Path) -> None:
    (tmp_path / "spain" / "catalonia").mkdir(parents=True)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert response.status_code == 404


def _write_grid(data_dir: Path, region: str,
                bbox: tuple[float, float, float, float]) -> None:
    (data_dir / "spain" / region).mkdir(parents=True, exist_ok=True)
    (data_dir / "spain" / region / "grid.json").write_text(
        json.dumps({"bbox": list(bbox), "chunk_m": 10000.0}))


def test_density_merges_regions_when_region_omitted(tmp_path: Path) -> None:
    cx, cy = to_utm(1.83, 41.59)
    _write_grid(tmp_path, "one", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_grid(tmp_path, "two", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_density(tmp_path, "one", 12)
    _write_density(tmp_path, "two", 12)

    client = TestClient(create_app(data_dir=tmp_path))
    response = client.get("/density", params={
        "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert response.status_code == 200
    assert len(response.json()["features"]) == 2


def test_density_sums_requested_length_and_exposure_buckets(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12,
                   hist=[(10, 3, 0, 2), (20, 4, 0, 1)])
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7",
        "min_len": 100, "max_len": 200, "min_exposure": 30,
    })

    assert response.json()["features"][0]["properties"]["n_pairs"] == 2


def test_density_returns_length_bounds_from_the_filtered_histogram(
        tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12,
                   hist=[(2, 3, 0, 1), (9, 3, 0, 2), (100, 3, 0, 4)])
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7",
        "min_len": 20, "max_len": 100, "min_exposure": 30,
    })

    properties = response.json()["features"][0]["properties"]
    assert properties["n_pairs"] == 3
    assert properties["length_min"] == 20.0
    assert properties["length_max"] == 100.0


def test_density_excludes_each_selected_layer_bit(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12,
                   hist=[(10, 3, 1, 2), (10, 3, 4, 3), (10, 3, 0, 5)])
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7",
        "min_len": 100, "max_len": 200, "min_exposure": 30,
        "exclude_layers": "zepa,enp",
    })

    assert response.json()["features"][0]["properties"]["n_pairs"] == 5


def test_density_omits_cells_the_filter_empties(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12, hist=[(10, 3, 0, 4)])
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7",
        "min_len": 300, "max_len": 400,
    })

    assert response.json()["features"] == []
