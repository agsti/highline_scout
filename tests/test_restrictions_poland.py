import json
from pathlib import Path

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Polygon

from highliner.etls.restriction import poland, shared

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def test_poland_restriction_specs_normalize_polish_names() -> None:
    source = gpd.GeoDataFrame({"nazwa": ["  Tatry  "]}, geometry=[_SQUARE],
                              crs="EPSG:4326")
    for spec in poland.SPECS.values():
        layer = shared.build_layer(source, spec)
        assert list(layer["name"]) == ["Tatry"]


def test_download_type_uses_stable_gid_order_for_pagination(
        monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[dict[str, str]] = []

    def fake_get(url: str, params: dict[str, str],
                 timeout: int) -> requests.Response:
        requested.append(params)
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"type":"FeatureCollection","features":[]}'
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    assert poland._download_type("GDOS:ParkiNarodowe") == []
    assert requested[0]["sortBy"] == "gid"


def test_poland_download_type_follows_full_pages(
        monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [[{"id": index} for index in range(poland._PAGE_SIZE)],
             [{"id": "last"}]]
    starts: list[str] = []

    def fake_get(url: str, params: dict[str, str],
                 timeout: int) -> requests.Response:
        starts.append(params["startIndex"])
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"features": pages.pop(0)}).encode()
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    features = poland._download_type("GDOS:ParkiNarodowe")

    assert len(features) == poland._PAGE_SIZE + 1
    assert features[-1] == {"id": "last"}
    assert starts == ["0", str(poland._PAGE_SIZE)]


def test_poland_loads_and_reprojects_local_geojson(tmp_path: Path) -> None:
    source = gpd.GeoDataFrame(
        {"nazwa": ["Test area"]}, geometry=[_square_3857()], crs="EPSG:3857")
    source.to_file(tmp_path / "zec.geojson", driver="GeoJSON")

    loaded = poland._load_source("zec", tmp_path)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326
    assert loaded.geometry.iloc[0].bounds[2] == pytest.approx(1.0, abs=1e-4)


def test_poland_rejects_unknown_or_missing_local_source(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="unknown"):
        poland._load_source("unknown", tmp_path)
    with pytest.raises(FileNotFoundError, match="no zec source"):
        poland._load_source("zec", tmp_path)


def _square_3857() -> Polygon:
    return Polygon([(0, 0), (0, 111_325.14),
                    (111_319.49, 111_325.14), (111_319.49, 0)])
