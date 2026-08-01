import json
from pathlib import Path

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Polygon

from highliner.etls.restriction.malta import main as malta


def test_malta_download_source_uses_the_official_wfs(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_get(url: str, params: dict[str, str], timeout: int) -> requests.Response:
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"type":"FeatureCollection","features":[{"id":"one"}]}'
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    malta._download_source("natura", tmp_path)

    features = json.loads((tmp_path / "natura.geojson").read_text())["features"]
    assert features == [{"id": "one"}]


def test_malta_loads_epsg_4258_source_as_wgs84(tmp_path: Path) -> None:
    source = gpd.GeoDataFrame({"siteName": ["Test site"]},
                              geometry=[Polygon([(14, 35), (14, 36),
                                                 (15, 36), (15, 35)])],
                              crs="EPSG:4258")
    source.to_file(tmp_path / "natura.geojson", driver="GeoJSON")

    loaded = malta._load_source("natura", tmp_path)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326
    assert loaded["siteName"].tolist() == ["Test site"]
