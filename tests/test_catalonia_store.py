import json
from pathlib import Path
import pytest
from fastapi import HTTPException
from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.repositories import catalonia_store as store
from highliner.repositories.anchors import save_anchors
from highliner.repositories.candidates import save_candidates


def _grid(tmp_path: Path) -> Path:
    region = tmp_path / "catalonia"
    region.mkdir()
    (region / "grid.json").write_text(json.dumps(
        {"bbox": [0.0, 0.0, 30000.0, 20000.0], "chunk_m": 10000.0}))
    return region


def test_read_grid(tmp_path: Path) -> None:
    g = store.read_grid(_grid(tmp_path))
    assert g.bbox == (0.0, 0.0, 30000.0, 20000.0)
    assert g.chunk_m == 10000.0


def test_chunk_indices_for_bbox(tmp_path: Path) -> None:
    g = store.read_grid(_grid(tmp_path))
    idx = store.chunk_indices_for_bbox(g, (8000.0, 1000.0, 12000.0, 2000.0))
    assert set(idx) == {(0, 0), (1, 0)}


def test_chunk_indices_clipped_to_grid(tmp_path: Path) -> None:
    g = store.read_grid(_grid(tmp_path))
    idx = store.chunk_indices_for_bbox(g, (-9e9, -9e9, 9e9, 9e9))
    assert set(idx) == {(cx, cy) for cx in range(3) for cy in range(2)}


def _cand(x: float) -> Candidate:
    a = Anchor(x=x, y=5000.0, elev=100.0, sectors=())
    b = Anchor(x=x + 40.0, y=5000.0, elev=100.0, sectors=())
    return Candidate(a=a, b=b, length=40.0, exposure=60.0, height_diff=0.0)


def test_load_anchors_in_bbox_only_overlapping(tmp_path: Path) -> None:
    region = _grid(tmp_path)
    (region / "anchors").mkdir()
    save_anchors([Anchor(x=5000.0, y=5000.0, elev=10.0, sectors=())],
                 region / "anchors" / "p_0_0.parquet")
    save_anchors([Anchor(x=15000.0, y=5000.0, elev=20.0, sectors=())],
                 region / "anchors" / "p_1_0.parquet")
    got = store.load_anchors_in_bbox(region, (0.0, 0.0, 9999.0, 10000.0))
    assert [round(a.x) for a in got] == [5000]


def test_load_pairs_in_bbox_only_overlapping(tmp_path: Path) -> None:
    region = _grid(tmp_path)
    (region / "pairs").mkdir()
    save_candidates([_cand(5000.0)], region / "pairs" / "q_0_0.parquet")
    save_candidates([_cand(15000.0)], region / "pairs" / "q_1_0.parquet")
    got = store.load_pairs_in_bbox(region, (0.0, 0.0, 9999.0, 10000.0))
    assert [round(c.a.x) for c in got] == [5000]


def test_load_pairs_too_many_chunks_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    region = _grid(tmp_path)
    (region / "pairs").mkdir()
    save_candidates([_cand(5000.0)], region / "pairs" / "q_0_0.parquet")
    monkeypatch.setattr(config, "MAX_VIEW_CHUNKS", 1)
    with pytest.raises(HTTPException) as ei:
        store.load_pairs_in_bbox(region, (0.0, 0.0, 30000.0, 20000.0))
    assert ei.value.status_code == 413
