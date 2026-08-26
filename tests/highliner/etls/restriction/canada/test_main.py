import json
import runpy
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Point


def test_canada_restrictions_write_cpcad_overlay(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction.canada import main as canada

    source = gpd.GeoDataFrame({"NAME_E": ["Test reserve"]},
                              geometry=[Point(-120, 50)], crs="EPSG:4326")
    monkeypatch.setattr(canada, "download_sources", lambda _raw: None)
    monkeypatch.setattr(canada, "_load_source", lambda _raw: source)

    canada.main(["--data-dir", str(tmp_path)])

    assert (tmp_path / "canada" / "restrictions" / "ca_protected.parquet").exists()


def test_download_sources_queries_cpcad_once_and_reuses_the_raw_file(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction.canada import main as canada

    body: dict[str, object] = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"NAME_E": "Test reserve"},
         "geometry": {"type": "Point", "coordinates": [-120.0, 50.0]}}]}
    calls: list[dict[str, str]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return body

    def fake_get(url: str, *, params: dict[str, str], timeout: float) -> Response:
        calls.append(params)
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    canada.download_sources(tmp_path)
    canada.download_sources(tmp_path)   # second call reuses the raw file

    assert len(calls) == 1
    assert calls[0]["f"] == "geojson"
    assert json.loads((tmp_path / "cpcad.geojson").read_text()) == body


def test_load_source_reprojects_to_wgs84_and_assumes_it_when_undeclared(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction.canada import main as canada

    # CPCAD serves EPSG:3978 when asked for its native projection; whatever
    # comes back has to end up in WGS84 for the shared layer writer.
    gpd.GeoDataFrame({"NAME_E": ["Lambert"]}, geometry=[Point(-1e6, 2e6)],
                     crs="EPSG:3978").to_file(tmp_path / "cpcad.geojson",
                                              driver="GeoJSON")
    assert canada._load_source(tmp_path).crs.to_epsg() == 4326

    bare = gpd.GeoDataFrame({"NAME_E": ["Bare"]}, geometry=[Point(-120, 50)])
    monkeypatch.setattr(gpd, "read_file", lambda _path: bare)
    assert canada._load_source(tmp_path).crs.to_epsg() == 4326


def test_canada_restriction_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.restriction.canada.main.main") as entry:
        runpy.run_module("highliner.etls.restriction.canada.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
