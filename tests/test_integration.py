from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from highliner.server.app import create_app

from highliner.etls.chunk import shared


def _patch_gap_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make dtm._download_tile synthesize terrain: plateau 100 m with a deep
    N-S trench (elev 20, 40 m wide) through the middle, so facing anchors exist
    across the trench (exposure ~80)."""
    from highliner.etls.chunk import dtm as _dtm

    def fake(bbox: tuple[float, float, float, float], width: int, height: int,
             dest: Path) -> Path:
        minx, miny, maxx, maxy = bbox
        cell = (maxx - minx) / width
        rows = []
        for _ in range(height):
            cells = []
            for c in range(width):
                x = minx + (c + 0.5) * cell
                cells.append("20.0" if 420130.0 <= x <= 420170.0 else "100.0")
            rows.append(" ".join(cells))
        header = [f"NCOLS {width}", f"NROWS {height}",
                  f"XLLCORNER {minx}", f"YLLCORNER {miny}",
                  f"CELLSIZE {cell}", "NODATA_VALUE -9999"]
        dest.write_text("\n".join(header) + "\n" + "\n".join(rows) + "\n")
        return dest
    monkeypatch.setattr(_dtm, "_download_tile", fake)


def test_full_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gap_download(monkeypatch)
    bbox = (420000.0, 4600000.0, 420300.0, 4600300.0)
    n = shared.precompute("spain", "demo", bbox, tmp_path, chunk_m=10000.0,
                          crs="EPSG:25831", dtm_source="icgc")
    assert n == 1

    client = TestClient(create_app(data_dir=tmp_path))
    fc = client.get("/zones", params={
        "region": "demo", "bbox": "420000,4600000,420300,4600300",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    }).json()
    assert fc["features"], "expected a zone across the gap"
    best = fc["features"][0]["properties"]
    assert best["height_max"] >= 50
