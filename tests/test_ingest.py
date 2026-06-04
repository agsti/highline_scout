import numpy as np
import rasterio
from rasterio.transform import from_origin
from highliner import ingest


def _write_tif(path):
    data = np.tile(np.arange(20, dtype="float32"), (20, 1))
    transform = from_origin(420000, 4600020, 2.0, 2.0)
    with rasterio.open(path, "w", driver="GTiff", height=20, width=20,
                       count=1, dtype="float32", crs="EPSG:25831",
                       transform=transform) as ds:
        ds.write(data, 1)


def test_fetch_caches_and_returns_path(tmp_path, monkeypatch):
    calls = []

    def fake_download(bbox, dest):
        calls.append(bbox)
        _write_tif(dest)
        return dest
    monkeypatch.setattr(ingest, "_download_dtm", fake_download)

    bbox = (420000, 4600000, 420040, 4600040)
    p1 = ingest.fetch_dtm(bbox, region="test", data_dir=tmp_path)
    assert p1.exists()
    # second call hits cache, no new download
    p2 = ingest.fetch_dtm(bbox, region="test", data_dir=tmp_path)
    assert p1 == p2
    assert len(calls) == 1
