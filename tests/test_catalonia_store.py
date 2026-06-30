import json
from pathlib import Path
import pytest
from highliner.repositories import catalonia_store as store


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
