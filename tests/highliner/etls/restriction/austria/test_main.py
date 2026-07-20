from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from highliner.etls.restriction.austria import main as austria


def test_austria_restriction_source_urls_are_national_open_data_layers() -> None:
    assert set(austria.SPECS) == {"zepa", "zec", "enp"}
    assert all("FeatureServer" in url for url in austria.SOURCE_URLS.values())


def test_austria_downloads_missing_geojson_source(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[str] = []

    def fake_download(url: str, path: Path) -> None:
        seen.append(url)
        path.write_text('{"type":"FeatureCollection","features":[]}')

    monkeypatch.setattr(austria, "_download", fake_download)
    austria.download_sources(tmp_path)

    assert set(path.name for path in tmp_path.glob("*.geojson")) == {
        "ffh.geojson", "vsr.geojson", "np.geojson"}
    assert set(seen) == set(austria.SOURCE_URLS.values())


def test_austria_loads_and_reprojects_local_source(tmp_path: Path) -> None:
    source = gpd.GeoDataFrame(
        {"SG_NAME": ["Test area"]},
        geometry=[Point(111_319.49, 111_325.14)],
        crs="EPSG:3857",
    )
    source.to_file(tmp_path / austria.SOURCE_FILES["zec"], driver="GeoJSON")

    loaded = austria._load_source("zec", tmp_path)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326
    assert loaded.geometry.iloc[0].x == pytest.approx(1.0, abs=1e-4)
    assert loaded.geometry.iloc[0].y == pytest.approx(1.0, abs=1e-4)
