import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from highliner.core.density import layer_mask
from highliner.etls.restriction.japan import main as japan


def test_japan_uses_moe_national_protected_area_downloads() -> None:
    assert set(japan.SPECS) == {"jp_national_parks", "jp_wildlife_areas"}
    assert all("biodic.go.jp" in url for url in japan.SOURCE_URLS.values())


def test_japan_layers_have_density_bits() -> None:
    for layer in japan.SPECS:
        assert layer_mask([layer]) != 0


def test_japan_download_sources_extracts_each_missing_archive_once(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    downloaded: list[Path] = []

    def make_archive(url: str, archive: Path) -> None:
        downloaded.append(archive)
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("source/areas.shp", b"shape")

    monkeypatch.setattr(japan, "_download", make_archive)

    japan.download_sources(tmp_path)
    for archive in tmp_path.glob("*.zip"):
        archive.unlink()
    japan.download_sources(tmp_path)

    assert sorted(path.name for path in downloaded) == [
        "jp_national_parks.zip", "jp_wildlife_areas.zip"]
    assert all(list((tmp_path / layer).rglob("*.shp"))
               for layer in japan.SOURCE_URLS)


def test_japan_load_source_assigns_wgs84_when_source_crs_is_missing(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = gpd.GeoDataFrame({"NAME": ["Park"]}, geometry=[Point(1, 2)])
    layer_dir = tmp_path / "jp_national_parks"
    layer_dir.mkdir()
    (layer_dir / "areas.shp").touch()
    monkeypatch.setattr(gpd, "read_file", lambda path: source)

    loaded = japan._load_source("jp_national_parks", tmp_path)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326
    assert loaded.geometry.iloc[0] == Point(1, 2)


def test_japan_restriction_main_writes_normalized_layers(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = gpd.GeoDataFrame(
        {"NAME": ["  Fuji National Park  "]}, geometry=[Point(138, 35)],
        crs="EPSG:4326")
    monkeypatch.setattr(japan, "download_sources", lambda raw_dir: None)
    monkeypatch.setattr(japan, "_load_source", lambda layer, raw_dir: source)

    japan.main(["--data-dir", str(tmp_path)])

    output = tmp_path / "japan" / "restrictions"
    for layer in japan.SPECS:
        written = gpd.read_parquet(output / f"{layer}.parquet")
        assert list(written["name"]) == ["Fuji National Park"]
