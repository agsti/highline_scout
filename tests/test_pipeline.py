import numpy as np
import rasterio
from rasterio.transform import from_origin
from highliner import pipeline
from highliner.anchors import load_anchors


def _write_mosaic(path):
    # two-sided cliff -> anchors exist
    data = np.full((61, 61), 40.0, dtype="float32")
    data[:, 28:33] = 100.0
    with rasterio.open(path, "w", driver="GTiff", height=61, width=61, count=1,
                       dtype="float32", crs="EPSG:25831",
                       transform=from_origin(0, 122, 2.0, 2.0)) as ds:
        ds.write(data, 1)


def test_analyze_area_runs_and_reports(tmp_path, monkeypatch):
    region_dir = tmp_path / "demo"
    region_dir.mkdir()

    def fake_fetch(bbox, region, data_dir, progress=None):
        path = region_dir / "mosaic.tif"
        _write_mosaic(path)
        if progress:
            progress(1, 1)
        return path
    monkeypatch.setattr(pipeline.ingest, "fetch_dtm", fake_fetch)

    phases = []
    n = pipeline.analyze_area((0, 0, 122, 122), "demo", tmp_path,
                              report=lambda ph, d, t: phases.append(ph))
    assert n > 0
    assert load_anchors(region_dir / "anchors.parquet")
    assert "downloading" in phases and "extracting" in phases
    assert phases.index("downloading") < phases.index("extracting")
