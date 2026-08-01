from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.luxembourg import main as luxembourg

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


@pytest.mark.parametrize("layer", ["zepa", "zec", "enp"])
def test_luxembourg_restriction_specs_keep_features(layer: str) -> None:
    name_field = luxembourg.SPECS[layer].name_field
    source = gpd.GeoDataFrame({name_field: ["  Reserve  "]},
                              geometry=[_SQUARE], crs="EPSG:4326")
    built = shared.build_layer(source, luxembourg.SPECS[layer])
    assert list(built["name"]) == ["Reserve"]


def test_luxembourg_main_downloads_then_writes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(luxembourg, "download_sources",
                        lambda raw_dir: calls.append(raw_dir))
    monkeypatch.setattr(luxembourg.shared, "write_layers", lambda *args: {})

    luxembourg.main(["--data-dir", str(tmp_path)])

    assert calls == [tmp_path / "luxembourg" / "restrictions" / "raw"]


def test_luxembourg_zpin_loader_assigns_declared_laea_crs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "zpin.gml"
    path.write_text("placeholder")
    source = gpd.GeoDataFrame(
        {"sitename0_geographicalname_spelling0_spellingofname_text": ["ZPIN"]},
        geometry=[Polygon([(4_000_000, 3_000_000), (4_000_001, 3_000_000),
                          (4_000_001, 3_000_001), (4_000_000, 3_000_001)])],
    )
    monkeypatch.setattr(gpd, "read_file", lambda _: source.copy())
    loaded = luxembourg._load_source("enp", tmp_path)
    assert loaded.crs.to_epsg() == 4326
