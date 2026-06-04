import numpy as np
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from highliner.anchors import Anchor, save_anchors
from highliner import api


def _setup_region(data_dir):
    region = data_dir / "test"
    region.mkdir(parents=True)
    # DTM: plateau 100 with a gap (20) between x cols 31..69 (2m px from origin)
    data = np.full((101, 101), 100.0, dtype="float32")
    data[:, 31:70] = 20.0
    transform = from_origin(0, 202, 2.0, 2.0)
    with rasterio.open(region / "mosaic.tif", "w", driver="GTiff",
                       height=101, width=101, count=1, dtype="float32",
                       crs="EPSG:25831", transform=transform) as ds:
        ds.write(data, 1)
    # two facing anchors across the gap (UTM coords)
    a = Anchor(x=60.0, y=100.0, elev=100.0, sectors=((80, 100, 60),))
    b = Anchor(x=140.0, y=100.0, elev=100.0, sectors=((260, 280, 60),))
    save_anchors([a, b], region / "anchors.parquet")


def test_candidates_endpoint(tmp_path):
    _setup_region(tmp_path)
    app = api.create_app(data_dir=tmp_path)
    client = TestClient(app)

    assert "test" in client.get("/regions").json()["regions"]

    r = client.get("/candidates", params={
        "region": "test",
        "bbox": "0,0,300,300",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
