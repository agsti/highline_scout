"""Tests for Slovenia's protected-area adapter."""

from collections.abc import Iterable
from pathlib import Path

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.slovenia import main as slovenia

_SQUARE = Polygon([(14.5, 46.0), (14.5, 46.1), (14.6, 46.1), (14.6, 46.0)])


def _source() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"NAME": ["Triglav"]}, geometry=[_SQUARE],
                            crs="EPSG:4326")


def test_slovenia_restrictions_use_official_arso_atom_exports() -> None:
    assert set(slovenia.SPECS) == {"zepa", "zec", "enp"}
    assert all("gis.arso.gov.si" in url for url in slovenia.SOURCE_URLS.values())


def test_slovenia_specs_name_features_from_the_arso_name_column() -> None:
    built = shared.build_layer(_source(), slovenia.SPECS["zepa"])

    assert list(built["name"]) == ["Triglav"]


def test_load_source_reprojects_to_wgs84(tmp_path: Path) -> None:
    _source().to_crs("EPSG:3794").to_file(tmp_path / "zepa.geojson",
                                          driver="GeoJSON")

    loaded = slovenia._load_source("zepa", tmp_path)

    assert loaded.crs.to_epsg() == 4326
    assert list(loaded["NAME"]) == ["Triglav"]


def test_load_source_reads_the_enp_archive_by_its_zip_suffix(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    read: list[Path] = []

    def fake_read_file(path: Path) -> gpd.GeoDataFrame:
        read.append(Path(path))
        return _source()

    monkeypatch.setattr(gpd, "read_file", fake_read_file)

    slovenia._load_source("enp", tmp_path)

    assert read == [tmp_path / "enp.zip"]


def test_load_source_rejects_a_source_without_a_crs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gpd, "read_file",
                        lambda _path: gpd.GeoDataFrame({"NAME": ["Triglav"]},
                                                       geometry=[_SQUARE]))

    with pytest.raises(ValueError, match="no CRS"):
        slovenia._load_source("zepa", tmp_path)


def test_load_source_requires_a_downloaded_file(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="No such file or directory"):
        slovenia._load_source("zepa", tmp_path)


def test_download_writes_the_response_body(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        content = b"payload"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(requests, "get",
                        lambda _url, timeout: Response())

    slovenia._download("https://example.invalid/x", tmp_path / "out.geojson")

    assert (tmp_path / "out.geojson").read_bytes() == b"payload"


def test_download_sources_skips_files_already_present(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for name in ("zepa.geojson", "zec.geojson", "enp.zip"):
        (raw_dir / name).write_text("{}")

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not re-download an existing source")

    monkeypatch.setattr(slovenia, "_download", boom)

    slovenia.download_sources(raw_dir)


def test_download_sources_fetches_each_missing_source(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw_dir = tmp_path / "raw"
    fetched: list[Path] = []

    def fake_download(_url: str, dest: Path) -> None:
        fetched.append(dest)
        dest.write_text("{}")

    monkeypatch.setattr(slovenia, "_download", fake_download)

    slovenia.download_sources(raw_dir)

    assert {path.name for path in fetched} == {
        "zepa.geojson", "zec.geojson", "enp.zip"}


def test_restriction_main_downloads_then_writes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    downloaded: list[Path] = []
    written: list[tuple[set[str], Path]] = []

    def fake_write(specs: Iterable[shared.LayerBuildSpec], _loader: object,
                   dest: Path) -> dict[str, Path]:
        written.append(({spec.id for spec in specs}, dest))
        return {}

    monkeypatch.setattr(slovenia, "download_sources",
                        lambda raw_dir: downloaded.append(raw_dir))
    monkeypatch.setattr(slovenia.shared, "write_layers", fake_write)

    slovenia.main(["--data-dir", str(tmp_path)])

    restrictions = tmp_path / "slovenia" / "restrictions"
    assert downloaded == [restrictions / "raw"]
    assert written == [({"zepa", "zec", "enp"}, restrictions)]


def test_restriction_main_loader_reads_from_the_raw_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[tuple[str, Path]] = []

    def fake_write(_specs: Iterable[shared.LayerBuildSpec], loader: object,
                   _dest: Path) -> dict[str, Path]:
        assert callable(loader)
        loader("zepa")
        return {}

    monkeypatch.setattr(slovenia, "download_sources", lambda _raw_dir: None)
    monkeypatch.setattr(slovenia, "_load_source",
                        lambda key, raw_dir: loaded.append((key, raw_dir)))
    monkeypatch.setattr(slovenia.shared, "write_layers", fake_write)

    slovenia.main(["--data-dir", str(tmp_path)])

    assert loaded == [("zepa", tmp_path / "slovenia" / "restrictions" / "raw")]
