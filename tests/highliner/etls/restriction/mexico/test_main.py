from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from highliner.core.density import layer_mask


def test_mexico_layer_is_registered_for_density() -> None:
    assert layer_mask(["mx_anp"]) != 0


def test_mexico_load_source_uses_conanp_name(
        tmp_path: Path) -> None:
    from highliner.etls.restriction.mexico import main as mexico
    source = gpd.GeoDataFrame({"NOMBRE": ["  Reserva  "]}, geometry=[Point(-100, 20)],
                              crs="EPSG:4326")
    source.to_file(tmp_path / "anp.shp")

    loaded = mexico._load_source("anp", tmp_path)

    assert list(loaded["NOMBRE"]) == ["Reserva"]


def test_mexico_restriction_main_writes_conanp_layer(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction.mexico import main as mexico
    written: list[set[str]] = []
    monkeypatch.setattr(mexico, "download_sources", lambda _path: None)
    monkeypatch.setattr(
        mexico.shared, "write_layers",
        lambda specs, _load, _dest: written.append({spec.id for spec in specs}))

    mexico.main(["--data-dir", str(tmp_path)])

    assert written == [{"mx_anp"}]
