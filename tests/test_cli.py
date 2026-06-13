from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from highliner import cli
from highliner.repositories.anchors import load_anchors


def test_analyze_writes_anchors(tmp_path: Path) -> None:
    region = tmp_path / "demo"
    region.mkdir()
    # two-sided cliff so anchors exist
    data = np.full((61, 61), 40.0, dtype="float32")
    data[:, 28:33] = 100.0
    with rasterio.open(region / "mosaic.tif", "w", driver="GTiff", height=61,
                       width=61, count=1, dtype="float32", crs="EPSG:25831",
                       transform=from_origin(0, 122, 2.0, 2.0)) as ds:
        ds.write(data, 1)

    cli.main(["analyze", "--region", "demo", "--data-dir", str(tmp_path)])
    anchors = load_anchors(region / "anchors.parquet")
    assert len(anchors) > 0
