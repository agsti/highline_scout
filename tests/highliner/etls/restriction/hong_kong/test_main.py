"""Tests for Hong Kong's protected-area adapter."""

from pathlib import Path

import pytest
import requests

from highliner.core.density import layer_mask


def test_hong_kong_country_parks_are_density_filterable() -> None:
    from highliner.etls.restriction.hong_kong import main as hong_kong

    assert set(hong_kong.SPECS) == {"hk_country_parks"}
    assert layer_mask(hong_kong.SPECS) != 0


def test_hong_kong_country_park_metadata_explains_rigging_effect() -> None:
    from highliner.core.restrictions import LAYERS

    layer = LAYERS["hk_country_parks"]
    assert layer["highlight"] in layer["tooltip"]
    assert "rigging" in layer["highlight"].lower()


_GEOJSON = """{
  "type": "FeatureCollection",
  "features": [
    {"type": "Feature",
     "properties": {"name_eng": "  Tai Mo Shan Country Park  ",
                    "realm": "Terrestrial"},
     "geometry": {"type": "Polygon", "coordinates":
        [[[114.1, 22.4], [114.1, 22.5], [114.2, 22.5], [114.2, 22.4],
          [114.1, 22.4]]]}},
    {"type": "Feature",
     "properties": {"name_eng": "Hoi Ha Wan Marine Park", "realm": "Marine"},
     "geometry": {"type": "Polygon", "coordinates":
        [[[114.3, 22.4], [114.3, 22.5], [114.4, 22.5], [114.4, 22.4],
          [114.3, 22.4]]]}}
  ]
}"""


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        pass


def test_download_sources_queries_the_hong_kong_subset(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction.hong_kong import main as hong_kong

    seen: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> _Response:
        seen.append({"url": url, **kwargs})
        return _Response(_GEOJSON.encode())

    monkeypatch.setattr(requests, "get", fake_get)
    raw_dir = tmp_path / "raw"

    hong_kong.download_sources(raw_dir)

    assert (raw_dir / hong_kong.SOURCE_FILE).read_bytes() == _GEOJSON.encode()
    assert seen[0]["url"] == hong_kong.SOURCE_URL
    assert seen[0]["params"] == {
        "where": "iso3='HKG'", "outFields": "*", "f": "geojson",
    }


def test_download_sources_keeps_an_existing_download(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction.hong_kong import main as hong_kong

    def fail(*_args: object, **_kwargs: object) -> _Response:
        raise AssertionError("cached source must not be re-downloaded")

    monkeypatch.setattr(requests, "get", fail)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / hong_kong.SOURCE_FILE).write_bytes(b"cached")

    hong_kong.download_sources(raw_dir)

    assert (raw_dir / hong_kong.SOURCE_FILE).read_bytes() == b"cached"


def test_load_source_rejects_an_unknown_source(tmp_path: Path) -> None:
    from highliner.etls.restriction.hong_kong import main as hong_kong

    with pytest.raises(KeyError):
        hong_kong._load_source("marine_parks", tmp_path)


def test_load_source_reports_a_missing_download(tmp_path: Path) -> None:
    from highliner.etls.restriction.hong_kong import main as hong_kong

    with pytest.raises(FileNotFoundError, match="protected areas"):
        hong_kong._load_source("protected_areas", tmp_path)


def test_load_source_returns_wgs84_geometries(tmp_path: Path) -> None:
    from highliner.etls.restriction.hong_kong import main as hong_kong

    (tmp_path / hong_kong.SOURCE_FILE).write_text(_GEOJSON)

    frame = hong_kong._load_source("protected_areas", tmp_path)

    assert frame.crs.to_epsg() == 4326
    assert len(frame) == 2


def test_main_writes_terrestrial_country_parks_only(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import geopandas as gpd

    from highliner.etls.restriction.hong_kong import main as hong_kong

    monkeypatch.setattr(requests, "get",
                        lambda *_a, **_kw: _Response(_GEOJSON.encode()))

    hong_kong.main(["--data-dir", str(tmp_path)])

    layer = gpd.read_parquet(
        tmp_path / "hong_kong" / "restrictions" / "hk_country_parks.parquet")

    assert list(layer["name"]) == ["Tai Mo Shan Country Park"]
