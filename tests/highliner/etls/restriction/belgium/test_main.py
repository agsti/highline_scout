import runpy
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.belgium import main as belgium


def _sites() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"NAAM": ["  Kalmthoutse Heide  ", "Dijlevallei", "Zwin"],
         "TYPE": ["SPA", "SAC", "SPA"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])] * 3,
        crs="EPSG:4326")


def test_belgium_restrictions_reuse_natura_layer_ids() -> None:
    assert set(belgium.SPECS) == {"zepa", "zec"}


def test_belgium_specs_split_bird_and_habitat_designations() -> None:
    source = _sites()

    birds = shared.build_layer(source, belgium.SPECS["zepa"])
    habitats = shared.build_layer(source, belgium.SPECS["zec"])

    assert set(birds["name"]) == {"Kalmthoutse Heide", "Zwin"}
    assert set(habitats["name"]) == {"Dijlevallei"}


def test_belgium_specs_normalize_official_names() -> None:
    layer = shared.build_layer(_sites(), belgium.SPECS["zepa"])
    assert "Kalmthoutse Heide" in set(layer["name"])


def test_belgium_specs_read_both_layers_from_one_source() -> None:
    assert {spec.source for spec in belgium.SPECS.values()} == {"natura"}
    assert {spec.name_field for spec in belgium.SPECS.values()} == {"NAAM"}


def test_belgium_main_downloads_once_and_writes_both_overlays(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reads: list[object] = []

    def fake_read_file(path: object) -> gpd.GeoDataFrame:
        reads.append(path)
        return _sites()

    monkeypatch.setattr(
        "highliner.etls.restriction.belgium.main.gpd.read_file", fake_read_file)

    belgium.main(["--data-dir", str(tmp_path)])

    out = tmp_path / "belgium" / "restrictions"
    assert set(gpd.read_parquet(out / "zepa.parquet")["name"]) == {
        "Kalmthoutse Heide", "Zwin"}
    assert set(gpd.read_parquet(out / "zec.parquet")["name"]) == {"Dijlevallei"}
    # The remote WFS is read once; both layers come off the cached raw file.
    assert reads[0] == belgium.NATURA_URL
    raw = tmp_path / "belgium" / "restrictions" / "raw" / "natura.geojson"
    assert raw.exists()


def test_belgium_main_reuses_an_existing_raw_download(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    raw = tmp_path / "belgium" / "restrictions" / "raw"
    raw.mkdir(parents=True)
    _sites().to_file(raw / "natura.geojson", driver="GeoJSON")

    def fake_read_file(path: object) -> gpd.GeoDataFrame:
        assert path != belgium.NATURA_URL, "a cached raw file must not re-fetch"
        return _sites()

    monkeypatch.setattr(
        "highliner.etls.restriction.belgium.main.gpd.read_file", fake_read_file)

    belgium.main(["--data-dir", str(tmp_path)])

    out = tmp_path / "belgium" / "restrictions"
    assert (out / "zepa.parquet").exists()
    assert (out / "zec.parquet").exists()


def test_belgium_restriction_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.restriction.belgium.main.main") as entry:
        runpy.run_module("highliner.etls.restriction.belgium.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
