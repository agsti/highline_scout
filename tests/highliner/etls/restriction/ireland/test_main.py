import json
import runpy
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Polygon

from highliner.etls.restriction.ireland import main as ireland


def _feature(name: str) -> dict[str, object]:
    return {
        "type": "Feature",
        "properties": {"SITENAME": name},
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
        {"SITENAME": ["Cliffs of Moher"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])], crs=crs)


def test_ireland_restriction_adapter_uses_npws_designations() -> None:
    assert set(ireland.SPECS) == {"zepa", "zec", "enp"}
    assert all("NPWSDesignatedAreasWFS" in url for url in ireland.SOURCE_URLS.values())


def test_ireland_loads_and_reprojects_local_geojson(tmp_path: Path) -> None:
    _square("EPSG:2157").to_file(tmp_path / "zec.geojson", driver="GeoJSON")

    loaded = ireland._load_source("zec", tmp_path)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326


def test_ireland_load_source_assumes_irish_tm_when_crs_absent(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "zec.geojson").write_text("{}")   # presence check only
    # A raw file that parses without a CRS is treated as Irish TM (EPSG:2157).
    crsless = _square("EPSG:2157").set_crs(None, allow_override=True)
    monkeypatch.setattr(
        "highliner.etls.restriction.ireland.main.gpd.read_file",
        lambda _path: crsless)

    loaded = ireland._load_source("zec", tmp_path)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326


def test_ireland_rejects_unknown_or_missing_local_source(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="unknown"):
        ireland._load_source("unknown", tmp_path)
    with pytest.raises(FileNotFoundError, match="no zepa source"):
        ireland._load_source("zepa", tmp_path)


def test_download_sources_writes_each_layer_once_and_skips_existing(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal calls
        calls += 1
        return _wfs_response([_feature("Site")])

    monkeypatch.setattr(requests, "get", fake_get)

    ireland.download_sources(tmp_path)
    ireland.download_sources(tmp_path)   # second call reuses the raw files

    assert calls == len(ireland.SOURCE_URLS)
    written = json.loads((tmp_path / "zepa.geojson").read_text())
    assert len(written["features"]) == 1


def test_download_sources_rejects_empty_register(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get", lambda *a, **k: _wfs_response([]))
    with pytest.raises(RuntimeError, match="no features"):
        ireland.download_sources(tmp_path)


def test_ireland_main_writes_all_three_npws_overlays(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    features = [_feature("Slieve League"), _feature("Burren")]
    monkeypatch.setattr(requests, "get", lambda *a, **k: _wfs_response(features))

    ireland.main(["--data-dir", str(tmp_path)])

    out = tmp_path / "ireland" / "restrictions"
    for layer in ("zepa", "zec", "enp"):
        frame = gpd.read_parquet(out / f"{layer}.parquet")
        assert set(frame["name"]) == {"Slieve League", "Burren"}


def test_ireland_restriction_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.restriction.ireland.main.main") as entry:
        runpy.run_module("highliner.etls.restriction.ireland.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
