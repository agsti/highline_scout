from pathlib import Path

from fastapi.testclient import TestClient
from highliner.server.app import create_app

from tests.helpers import write_restriction_layer as _write_restriction_layer


def test_restriction_layers_are_scoped_to_country(tmp_path: Path) -> None:
    _write_restriction_layer(tmp_path, "zepa", "Montserrat",
                             (1.80, 41.55, 1.85, 41.62), country="spain")
    _write_restriction_layer(tmp_path, "zps", "Dolomites",
                             (11.80, 46.45, 11.85, 46.52), country="italy")
    client = TestClient(create_app(data_dir=tmp_path))

    assert [layer["id"] for layer in client.get(
        "/restrictions/layers", params={"country": "spain"}
    ).json()["layers"]] == ["zepa"]
    assert [layer["id"] for layer in client.get(
        "/restrictions/layers", params={"country": "italy"}
    ).json()["layers"]] == ["zps"]
    assert client.get(
        "/restrictions/layers", params={"country": "france"}
    ).json()["layers"] == []


def test_restrictions_in_view(tmp_path: Path) -> None:
    _write_restriction_layer(tmp_path, "zepa", "Montserrat",
                             (1.80, 41.55, 1.85, 41.62))
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/restrictions", params={
        "bbox_lonlat": "1.78,41.54,1.90,41.66", "layers": "zepa"})
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert props["layer"] == "zepa"
    assert props["name"] == "Montserrat"


def test_restrictions_filters_out_of_view(tmp_path: Path) -> None:
    _write_restriction_layer(tmp_path, "zepa", "Montserrat",
                             (1.80, 41.55, 1.85, 41.62))
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/restrictions", params={
        "bbox_lonlat": "2.50,42.00,2.60,42.10", "layers": "zepa"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_restrictions_missing_data_is_empty(tmp_path: Path) -> None:
    # No restrictions downloaded yet -> endpoint still works, returns nothing.
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/restrictions", params={"bbox_lonlat": "1.0,41.0,2.0,42.0"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_restrictions_scoped_to_country(tmp_path: Path) -> None:
    # A layer stored only under the france partition is invisible to the default
    # (spain) request, and served when france is requested.
    _write_restriction_layer(tmp_path, "zepa", "Écrins",
                             (1.80, 41.55, 1.85, 41.62), country="france")
    client = TestClient(create_app(data_dir=tmp_path))
    view = {"bbox_lonlat": "1.78,41.54,1.90,41.66", "layers": "zepa"}

    assert client.get("/restrictions", params=view).json()["features"] == []
    got = client.get("/restrictions", params={**view, "country": "france"})
    assert len(got.json()["features"]) == 1
    assert client.get("/restrictions", params={
        **view, "country": "france", "layers": "zps",
    }).json()["features"] == []
