import zipfile
from collections.abc import Iterable
from pathlib import Path

import geopandas as gpd
import pytest
from highliner.core.restrictions import LAYERS
from shapely.geometry import Polygon

from highliner.etls.restriction import shared

_SQUARE = Polygon([(2600000, 1200000), (2600000, 1201000),
                   (2601000, 1201000), (2601000, 1200000)])


def test_switzerland_specs_build_three_named_layers() -> None:
    from highliner.etls.restriction import switzerland

    source = gpd.GeoDataFrame(
        {"Name": ["  Alpine reserve  "]}, geometry=[_SQUARE], crs="EPSG:2056")

    assert set(switzerland.SPECS) == {
        "ch_game_reserves", "ch_bird_reserves", "ch_parks",
    }
    for spec in switzerland.SPECS.values():
        layer = shared.build_layer(source.to_crs(4326), spec)
        assert list(layer["name"]) == ["Alpine reserve"]


def test_load_source_reprojects_official_lv95_shape_to_wgs84(
        tmp_path: Path) -> None:
    from highliner.etls.restriction import switzerland

    source = gpd.GeoDataFrame(
        {"Name": ["Reserve"]}, geometry=[_SQUARE], crs="EPSG:2056")
    source.to_file(tmp_path / "N2023_Revision_jagdbann.shp")

    loaded = switzerland._load_source("game_reserves", tmp_path)

    assert loaded.crs.to_epsg() == 4326
    assert list(loaded["Name"]) == ["Reserve"]


def test_extract_flattened_discards_archive_directories(tmp_path: Path) -> None:
    from highliner.etls.restriction import switzerland

    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("nested/reserve.shp", b"shape")
        archive.writestr("nested/reserve.dbf", b"table")

    switzerland._extract_flattened(archive_path, tmp_path / "raw")

    assert (tmp_path / "raw" / "reserve.shp").read_bytes() == b"shape"
    assert (tmp_path / "raw" / "reserve.dbf").read_bytes() == b"table"


def test_restriction_main_downloads_then_writes(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction import switzerland

    downloaded: list[Path] = []
    written: list[tuple[set[str], Path]] = []

    def fake_write(specs: Iterable[shared.LayerBuildSpec], _loader: object,
                   dest: Path) -> dict[str, Path]:
        written.append(({spec.id for spec in specs}, dest))
        return {}

    monkeypatch.setattr(switzerland, "download_sources",
                        lambda raw_dir: downloaded.append(raw_dir))
    monkeypatch.setattr(switzerland.shared, "write_layers", fake_write)

    switzerland.main(["--data-dir", str(tmp_path)])

    restrictions = tmp_path / "switzerland" / "restrictions"
    assert downloaded == [restrictions / "raw"]
    assert written == [({
        "ch_game_reserves", "ch_bird_reserves", "ch_parks",
    }, restrictions)]


def test_swiss_layer_metadata_highlights_scouting_action() -> None:
    for layer_id in ("ch_game_reserves", "ch_bird_reserves", "ch_parks"):
        spec = LAYERS[layer_id]
        assert spec["highlight"] in spec["tooltip"]
        assert "rigging" in spec["highlight"].lower()
