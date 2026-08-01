import subprocess
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from highliner.etls.restriction.andorra import main as andorra


def test_andorra_restriction_source_is_the_government_natural_parks_layer() -> None:
    assert set(andorra.SPECS) == {"ad_natural_parks"}
    assert "iea.ad" in andorra.SOURCE_URL


def test_andorra_downloads_and_loads_natural_parks(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_download(url: str, destination: Path) -> None:
        assert url == andorra.SOURCE_URL
        destination.write_bytes(b"archive")

    def fake_extract(_args: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        assert check
        gpd.GeoDataFrame({"NOM": ["Sorteny"]}, geometry=[Point(0, 0)],
                         crs="EPSG:4326").to_file(tmp_path / "parks.shp")
        return subprocess.CompletedProcess([], 0)

    monkeypatch.setattr(andorra, "_download", fake_download)
    monkeypatch.setattr(andorra.subprocess, "run", fake_extract)
    andorra.download_source(tmp_path)

    loaded = andorra._load_source(tmp_path)
    assert list(loaded["NOM"]) == ["Sorteny"]
    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326
