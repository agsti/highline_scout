import runpy
import zipfile
from collections.abc import Iterable
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pytest
from shapely.geometry import Point

from highliner.etls.restriction import shared
from highliner.etls.restriction.cyprus import main as cyprus


def test_cyprus_natura_specs_split_birds_from_habitats() -> None:
    source = gpd.GeoDataFrame(
        {"naturaname": ["Birds", "Habitats"], "designatio": ["SPA", "SAC"]},
        geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326")

    birds = shared.build_layer(source, cyprus.SPECS["zepa"])
    habitats = shared.build_layer(source, cyprus.SPECS["zec"])

    assert list(birds["name"]) == ["Birds"]
    assert list(habitats["name"]) == ["Habitats"]


def test_cyprus_national_spec_uses_published_site_name_field() -> None:
    source = gpd.GeoDataFrame({"SITENAME": ["Dasos Sotira"]},
                              geometry=[Point(0, 0)], crs="EPSG:4326")

    protected = shared.build_layer(source, cyprus.SPECS["enp"])

    assert list(protected["name"]) == ["Dasos Sotira"]


def test_download_sources_extracts_each_archive_under_its_key(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlretrieve(url: str, dest: Path) -> None:
        key = "natura" if "Natura" in url else "national"
        with zipfile.ZipFile(dest, "w") as bundle:
            bundle.writestr(f"nested/{key}.shp", b"shp")
            bundle.writestr(f"nested/{key}.dbf", b"dbf")
            bundle.writestr("nested/", b"")

    monkeypatch.setattr(cyprus, "urlretrieve", fake_urlretrieve)

    cyprus._download_sources(tmp_path)

    # Members are flattened and prefixed, so the two sources cannot collide.
    assert (tmp_path / "natura_natura.shp").read_bytes() == b"shp"
    assert (tmp_path / "national_national.dbf").read_bytes() == b"dbf"
    assert not list(tmp_path.glob("*.zip"))


def test_download_sources_skips_a_key_already_on_disk(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "natura_sites.shp").write_bytes(b"shp")
    fetched: list[str] = []

    def fake_urlretrieve(url: str, dest: Path) -> None:
        fetched.append(url)
        with zipfile.ZipFile(dest, "w") as bundle:
            bundle.writestr("national.shp", b"shp")

    monkeypatch.setattr(cyprus, "urlretrieve", fake_urlretrieve)

    cyprus._download_sources(tmp_path)

    assert fetched == [cyprus.SOURCE_URLS["national"]]


def test_load_source_reprojects_to_wgs84(tmp_path: Path) -> None:
    projected = gpd.GeoDataFrame(
        {"naturaname": ["Akamas"], "designatio": ["SPA"]},
        geometry=[Point(500000.0, 3850000.0)], crs="EPSG:32636")
    projected.to_file(tmp_path / "natura_sites.shp")

    loaded = cyprus._load_source("natura", tmp_path)

    assert loaded.crs.to_epsg() == 4326
    assert list(loaded["naturaname"]) == ["Akamas"]


def test_load_source_rejects_an_unknown_key(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        cyprus._load_source("not_a_real_source", tmp_path)


def test_load_source_requires_a_downloaded_shapefile(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="natura"):
        cyprus._load_source("natura", tmp_path)


def test_restriction_main_downloads_then_writes_beside_raw(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    downloaded: list[Path] = []
    written: list[tuple[set[str], Path]] = []

    def fake_write(specs: Iterable[shared.LayerBuildSpec], _loader: object,
                   dest: Path) -> dict[str, Path]:
        written.append(({spec.id for spec in specs}, dest))
        return {}

    monkeypatch.setattr(cyprus, "_download_sources", downloaded.append)
    monkeypatch.setattr(shared, "write_layers", fake_write)

    cyprus.main(["--data-dir", str(tmp_path)])

    restrictions = tmp_path / "cyprus" / "restrictions"
    assert downloaded == [restrictions / "raw"]
    assert written == [({"zepa", "zec", "enp"}, restrictions)]


def test_cyprus_restriction_module_entry_point_calls_main() -> None:
    with patch("highliner.etls.restriction.cyprus.main.main") as entry:
        runpy.run_module("highliner.etls.restriction.cyprus.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
