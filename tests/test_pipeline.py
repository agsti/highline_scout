from pathlib import Path
from typing import Callable
import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from highliner.services import pipeline
from highliner.repositories import dtm
from highliner.repositories.anchors import load_anchors


def _write_mosaic(path: Path) -> None:
    # two-sided cliff -> anchors exist
    data = np.full((61, 61), 40.0, dtype="float32")
    data[:, 28:33] = 100.0
    with rasterio.open(path, "w", driver="GTiff", height=61, width=61, count=1,
                       dtype="float32", crs="EPSG:25831",
                       transform=from_origin(0, 122, 2.0, 2.0)) as ds:
        ds.write(data, 1)


def test_analyze_area_runs_and_reports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    region_dir = tmp_path / "demo"
    region_dir.mkdir()

    def fake_fetch(bbox: object, region: object, data_dir: object, progress: Callable[[int, int], None] | None = None) -> Path:
        path = region_dir / "mosaic.tif"
        _write_mosaic(path)
        if progress:
            progress(1, 1)
        return path
    monkeypatch.setattr(dtm, "fetch_dtm", fake_fetch)

    phases = []
    n = pipeline.analyze_area((0, 0, 122, 122), "demo", tmp_path,
                              report=lambda ph, d, t: phases.append(ph))
    assert n > 0
    assert load_anchors(region_dir / "anchors.parquet")
    assert "downloading" in phases and "extracting" in phases
    assert phases.index("downloading") < phases.index("extracting")
