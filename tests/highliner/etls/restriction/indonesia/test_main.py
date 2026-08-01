import json
from pathlib import Path

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.indonesia import main as indonesia

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def test_indonesia_restriction_spec_normalizes_name() -> None:
    source = gpd.GeoDataFrame({"FCODE": ["  Taman Nasional  "]},
                              geometry=[_SQUARE], crs="EPSG:4326")
    layer = shared.build_layer(source, indonesia.SPECS["id_kawasan_konservasi"])
    assert list(layer["name"]) == ["Taman Nasional"]


def test_indonesia_download_paginates_arcgis_features(
        monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [[{"id": index} for index in range(indonesia._PAGE_SIZE)],
             [{"id": "last"}]]
    offsets: list[int] = []

    def fake_get(url: str, params: dict[str, str | int],
                 timeout: int) -> requests.Response:
        offsets.append(int(params["resultOffset"]))
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"features": pages.pop(0)}).encode()
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    assert indonesia._download_features()[-1] == {"id": "last"}
    assert offsets == [0, indonesia._PAGE_SIZE]


def test_indonesia_loads_geojson_source(tmp_path: Path) -> None:
    source = gpd.GeoDataFrame({"FCODE": ["Test"]}, geometry=[_SQUARE],
                              crs="EPSG:4326")
    source.to_file(tmp_path / "kawasan_konservasi.geojson", driver="GeoJSON")

    loaded = indonesia._load_source("kawasan_konservasi", tmp_path)
    assert list(loaded["FCODE"]) == ["Test"]
