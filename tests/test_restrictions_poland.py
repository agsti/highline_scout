import geopandas as gpd
import pytest
import requests
from highliner.etls.restriction import poland, shared
from shapely.geometry import Polygon

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
