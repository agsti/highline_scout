import io
import runpy
import subprocess
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Point, Polygon

from highliner.etls.restriction.andorra import main as andorra


def _write_parks(directory: Path, crs: str | None = "EPSG:4326") -> None:
    square = Polygon([(1.5, 42.5), (1.6, 42.5), (1.6, 42.6), (1.5, 42.6)])
    gpd.GeoDataFrame({"NOM": ["Sorteny"]}, geometry=[square],
                     crs=crs).to_file(directory / "parks.shp")


def test_andorra_restriction_source_is_the_government_natural_parks_layer() -> None:
    assert set(andorra.SPECS) == {"ad_natural_parks"}
    assert "iea.ad" in andorra.SOURCE_URL


def test_andorra_downloads_and_loads_natural_parks(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_download(url: str, destination: Path) -> None:
        assert url == andorra.SOURCE_URL
        destination.write_bytes(b"archive")

    def fake_extract(args: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        assert check
        assert args[0] == "/fake/bin/unar"
        gpd.GeoDataFrame({"NOM": ["Sorteny"]}, geometry=[Point(0, 0)],
                         crs="EPSG:4326").to_file(tmp_path / "parks.shp")
        return subprocess.CompletedProcess([], 0)

    # Stub the lookup too, so the test does not need `unar` on the host.
    monkeypatch.setattr(andorra.shutil, "which", lambda _name: "/fake/bin/unar")
    monkeypatch.setattr(andorra, "_download", fake_download)
    monkeypatch.setattr(andorra.subprocess, "run", fake_extract)
    andorra.download_source(tmp_path)

    loaded = andorra._load_source(tmp_path)
    assert list(loaded["NOM"]) == ["Sorteny"]
    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326


def test_andorra_extraction_reports_a_missing_unar(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_download(_url: str, destination: Path) -> None:
        destination.write_bytes(b"archive")

    monkeypatch.setattr(andorra, "_download", fake_download)
    monkeypatch.setattr(andorra.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="unar"):
        andorra.download_source(tmp_path)


def test_andorra_download_streams_the_official_archive(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    response = requests.Response()
    response.status_code = 200
    response.raw = io.BytesIO(b"Rar!\x1a\x07\x00archive")
    monkeypatch.setattr(requests, "get",
                        lambda *args, **kwargs: response)
    destination = tmp_path / andorra.SOURCE_FILE

    andorra._download(andorra.SOURCE_URL, destination)

    assert destination.read_bytes() == b"Rar!\x1a\x07\x00archive"


def test_andorra_load_source_needs_an_extracted_shapefile(
        tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="natural-park shapefile"):
        andorra._load_source(tmp_path)


def test_andorra_load_source_rejects_a_shapefile_without_a_crs(
        tmp_path: Path) -> None:
    _write_parks(tmp_path, crs=None)

    with pytest.raises(ValueError, match="no CRS"):
        andorra._load_source(tmp_path)


def test_andorra_main_writes_the_natural_parks_overlay(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_download(_url: str, destination: Path) -> None:
        destination.write_bytes(b"archive")

    def fake_extract(args: list[str],
                     check: bool) -> subprocess.CompletedProcess[str]:
        _write_parks(Path(args[args.index("-o") + 1]))
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr(andorra.shutil, "which", lambda _name: "/fake/bin/unar")
    monkeypatch.setattr(andorra, "_download", fake_download)
    monkeypatch.setattr(andorra.subprocess, "run", fake_extract)

    andorra.main(["--data-dir", str(tmp_path)])

    out = tmp_path / "andorra" / "restrictions" / "ad_natural_parks.parquet"
    layer = gpd.read_parquet(out)
    assert list(layer["name"]) == ["Sorteny"]


def test_andorra_restriction_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.restriction.andorra.main.main") as entry:
        runpy.run_module("highliner.etls.restriction.andorra.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
