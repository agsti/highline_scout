from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from highliner.server.app import create_app

from highliner.core import config
from tests.helpers import facing_pair as _facing_pair
from tests.helpers import gap_region as _gap_region
from tests.helpers import write_region as _write_region


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
