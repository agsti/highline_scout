from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from highliner import cli
from highliner.app import create_app


def test_full_pipeline(tmp_path: Path) -> None:
    region = tmp_path / "demo"
    region.mkdir()
    # plateau 100m with a deep central gap -> two facing rims, one good line
    data = np.full((151, 151), 100.0, dtype="float32")
    data[:, 60:90] = 20.0
    with rasterio.open(region / "mosaic.tif", "w", driver="GTiff", height=151,
                       width=151, count=1, dtype="float32", crs="EPSG:25831",
                       transform=from_origin(420000, 4600302, 2.0, 2.0)) as ds:
        ds.write(data, 1)

    cli.main(["analyze", "--region", "demo", "--data-dir", str(tmp_path)])

    client = TestClient(create_app(data_dir=tmp_path))
    fc = client.get("/zones", params={
        "region": "demo", "bbox": "420000,4600000,420302,4600302",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    }).json()
    assert fc["features"], "expected a zone across the gap"
    best = fc["features"][0]["properties"]
    assert best["height_max"] >= 50
