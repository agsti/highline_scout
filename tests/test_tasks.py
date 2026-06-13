import numpy as np
import rasterio
from rasterio.transform import from_origin
from highliner.tasks import analyze as tasks
from highliner.services import pipeline


def _write_mosaic(path):
    data = np.full((61, 61), 40.0, dtype="float32")
    data[:, 28:33] = 100.0
    with rasterio.open(path, "w", driver="GTiff", height=61, width=61, count=1,
                       dtype="float32", crs="EPSG:25831",
                       transform=from_origin(0, 122, 2.0, 2.0)) as ds:
        ds.write(data, 1)


def test_analyze_task_updates_jobstore(tmp_path, jobstore, monkeypatch):
    tasks.huey.immediate = True  # run inline, in-memory
    try:
        (tmp_path / "demo").mkdir()

        def fake_fetch(bbox, region, data_dir, progress=None):
            from pathlib import Path
            p = Path(data_dir) / region / "mosaic.tif"
            _write_mosaic(p)
            if progress:
                progress(1, 1)
            return p
        monkeypatch.setattr(pipeline.dtm, "fetch_dtm", fake_fetch)

        jid = jobstore.create("Demo", "demo")
        tasks.analyze_task((0, 0, 122, 122), "demo", str(tmp_path), jid)

        job = jobstore.get(jid)
        assert job["status"] == "done"
        assert "anchors" in job["message"]
    finally:
        tasks.huey.immediate = False


def test_analyze_task_records_error(tmp_path, jobstore, monkeypatch):
    tasks.huey.immediate = True
    try:
        def boom(bbox, region, data_dir, report=None):
            raise RuntimeError("icgc down")
        monkeypatch.setattr(tasks.pipeline, "analyze_area", boom)

        jid = jobstore.create("Demo", "demo")
        try:
            tasks.analyze_task((0, 0, 1, 1), "demo", str(tmp_path), jid)
        except RuntimeError:
            pass  # task re-raises after recording; immediate mode surfaces it

        job = jobstore.get(jid)
        assert job["status"] == "error"
        assert "icgc down" in job["error"]
    finally:
        tasks.huey.immediate = False
