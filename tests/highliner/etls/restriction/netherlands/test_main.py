import json
import runpy
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.netherlands import main as netherlands


def _feature(name: str, beschermin: str) -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {"naamN2K": name, "beschermin": beschermin},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
        },
    }


def _wfs_response(features: list[dict[str, object]]) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(
        {"type": "FeatureCollection", "features": features}).encode()
    return response


def _square(crs: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"naamN2K": ["  Sint Pietersberg  "], "beschermin": ["HR groeve"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])], crs=crs)


def test_netherlands_specs_split_birds_and_habitats_by_directive() -> None:
    source = gpd.GeoDataFrame(
        {"naamN2K": ["Birds only", "Habitats only", "Both", "Quarry"],
         "beschermin": ["VR", "HR", "VR+HR", "HR groeve"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])] * 4,
        crs="EPSG:4326")

    birds = shared.build_layer(source, netherlands.SPECS["zepa"])
    habitats = shared.build_layer(source, netherlands.SPECS["zec"])

    assert set(birds["name"]) == {"Birds only", "Both"}
    assert set(habitats["name"]) == {"Habitats only", "Both", "Quarry"}


def test_netherlands_specs_normalize_official_names() -> None:
    source = _square("EPSG:4326")
    assert list(shared.build_layer(source, netherlands.SPECS["zec"])["name"]) == [
        "Sint Pietersberg"
    ]


def test_netherlands_loads_and_reprojects_local_geojson(tmp_path: Path) -> None:
    path = tmp_path / "natura2000.geojson"
    _square("EPSG:28992").to_file(path, driver="GeoJSON")

    loaded = netherlands._load_source("natura2000", tmp_path)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326


def test_netherlands_load_source_assumes_rd_new_when_crs_absent(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "natura2000.geojson").write_text("{}")   # presence check only
    # A raw file that parses without a CRS is treated as RD New (EPSG:28992).
    crsless = _square("EPSG:28992").set_crs(None, allow_override=True)
    monkeypatch.setattr(
        "highliner.etls.restriction.netherlands.main.gpd.read_file",
        lambda _path: crsless)

    loaded = netherlands._load_source("natura2000", tmp_path)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326


def test_netherlands_rejects_unknown_or_missing_local_source(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="unknown"):
        netherlands._load_source("unknown", tmp_path)
    with pytest.raises(FileNotFoundError, match="no natura2000 source"):
        netherlands._load_source("natura2000", tmp_path)


def test_download_sources_writes_once_and_skips_existing(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal calls
        calls += 1
        return _wfs_response([_feature("Site", "VR+HR")])

    monkeypatch.setattr(requests, "get", fake_get)

    netherlands.download_sources(tmp_path)
    netherlands.download_sources(tmp_path)   # second call reuses the raw file

    assert calls == 1
    written = json.loads((tmp_path / "natura2000.geojson").read_text())
    assert len(written["features"]) == 1


def test_download_sources_rejects_empty_register(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _wfs_response([]))
    with pytest.raises(RuntimeError, match="no features"):
        netherlands.download_sources(tmp_path)


def test_netherlands_main_writes_both_natura2000_overlays(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    features = [_feature("Birds", "VR"), _feature("Habitats", "HR"),
                _feature("Both", "VR+HR")]
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _wfs_response(features))

    netherlands.main(["--data-dir", str(tmp_path)])

    out = tmp_path / "netherlands" / "restrictions"
    zepa = gpd.read_parquet(out / "zepa.parquet")
    zec = gpd.read_parquet(out / "zec.parquet")
    assert set(zepa["name"]) == {"Birds", "Both"}
    assert set(zec["name"]) == {"Habitats", "Both"}


def test_netherlands_restriction_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.restriction.netherlands.main.main") as entry:
        runpy.run_module("highliner.etls.restriction.netherlands.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
