from pathlib import Path

import geopandas as gpd
import pytest
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
