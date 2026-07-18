from pathlib import Path

import pytest
from highliner.etls.restriction import austria


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
