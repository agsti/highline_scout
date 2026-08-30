import json
import runpy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.belgium import main as belgium


def _sites() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": ["  Kalmthoutse Heide  ", "Dijlevallei", "Lesse et Lomme"],
         "designation": ["SPA", "SAC", "SPA,SAC"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])] * 3,
        crs="EPSG:4326")


def _feature(coords: list[tuple[float, float]], props: dict[str, Any]
             ) -> dict[str, Any]:
    ring = [list(point) for point in coords + [coords[0]]]
    return {"type": "Feature", "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [ring]}}


def _write_raw(raw_dir: Path, key: str, features: list[Any]) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{key}.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}))


def _seed_raw(raw_dir: Path) -> None:
    """One site per region, Flanders in Lambert 72 and Wallonia in WGS84."""
    _write_raw(raw_dir, "flanders_spa",
               [_feature([(160_000.0, 170_000.0), (160_100.0, 170_000.0),
                          (160_100.0, 170_100.0)], {"gebnaam": "  Zwin  "})])
    _write_raw(raw_dir, "flanders_sac",
               [_feature([(160_000.0, 170_000.0), (160_100.0, 170_000.0),
                          (160_100.0, 170_100.0)], {"naam": "Dijlevallei"})])
    _write_raw(raw_dir, "wallonia",
               [_feature([(5.0, 50.0), (5.1, 50.0), (5.1, 50.1)],
                         {"NOM": "Lesse et Lomme"})])


def test_belgium_restrictions_reuse_natura_layer_ids() -> None:
    assert set(belgium.SPECS) == {"zepa", "zec"}


def test_belgium_specs_split_bird_and_habitat_designations() -> None:
    source = _sites()

    birds = shared.build_layer(source, belgium.SPECS["zepa"])
    habitats = shared.build_layer(source, belgium.SPECS["zec"])

    assert set(birds["name"]) == {"Kalmthoutse Heide", "Lesse et Lomme"}
    assert set(habitats["name"]) == {"Dijlevallei", "Lesse et Lomme"}


def test_belgium_specs_normalize_official_names() -> None:
    layer = shared.build_layer(_sites(), belgium.SPECS["zepa"])
    assert "Kalmthoutse Heide" in set(layer["name"])


def test_belgium_specs_read_both_layers_from_one_merged_source() -> None:
    assert {spec.source for spec in belgium.SPECS.values()} == {"natura"}
    assert {spec.name_field for spec in belgium.SPECS.values()} == {"name"}


def test_load_source_merges_the_regions_into_wgs84(tmp_path: Path) -> None:
    _seed_raw(tmp_path)

    frame = belgium._load_source("natura", tmp_path)

    assert len(frame) == 3
    assert set(frame["designation"]) == {"SPA", "SAC", "SPA,SAC"}
    # Lambert 72 metres would still read as metres had the CRS not been forced.
    minx, miny, maxx, maxy = frame.total_bounds
    assert 2.0 < minx < 6.5 and 49.0 < miny < 52.0
    assert maxx < 6.5 and maxy < 52.0


def test_load_source_rejects_an_unknown_source(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        belgium._load_source("enp", tmp_path)


def test_download_flanders_reuses_a_cached_layer(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_raw(tmp_path, "flanders_spa", [_feature([(0, 0), (1, 0), (1, 1)],
                                                   {"gebnaam": "Zwin"})])

    def fail(*args: object, **kwargs: object) -> object:
        raise AssertionError("a cached raw file must not be re-fetched")

    monkeypatch.setattr(requests, "get", fail)

    belgium._download_flanders(tmp_path, "flanders_spa", "ps:ps_vglrl")


def test_download_flanders_rejects_an_empty_layer(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(belgium, "_get", lambda *a, **k: {"features": []})

    with pytest.raises(RuntimeError, match="no Natura 2000 features"):
        belgium._download_flanders(tmp_path, "flanders_spa", "ps:ps_vglrl")


def test_download_wallonia_pages_until_the_server_runs_out(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    offsets: list[object] = []
    page = [_feature([(5, 50), (5.1, 50), (5.1, 50.1)], {"NOM": "site"})]

    def fake_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
        offsets.append(params["resultOffset"])
        full = page * belgium.WALLONIA_PAGE
        return {"features": full if len(offsets) == 1 else page}

    monkeypatch.setattr(belgium, "_get", fake_get)

    belgium._download_wallonia(tmp_path)

    assert offsets == [0, belgium.WALLONIA_PAGE]
    written = json.loads((tmp_path / "wallonia.geojson").read_text())
    assert len(written["features"]) == belgium.WALLONIA_PAGE + 1


def test_download_wallonia_surfaces_an_arcgis_error_body(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # ArcGIS reports its own failures inside an HTTP 200 response.
    monkeypatch.setattr(belgium, "_get",
                        lambda *a, **k: {"error": {"message": "Pagination"}})

    with pytest.raises(RuntimeError, match="Pagination"):
        belgium._download_wallonia(tmp_path)


def test_get_retries_a_transient_failure(
        monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def fake_get(url: str, params: object, timeout: int) -> requests.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.Timeout("temporary")
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"features": []}'
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(
        "highliner.etls.restriction.belgium.main.time.sleep", lambda _: None)

    assert belgium._get("https://example/wfs", {}) == {"features": []}
    assert attempts == 2


def test_get_gives_up_after_the_last_attempt(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests, "get", _always_timeout)
    monkeypatch.setattr(
        "highliner.etls.restriction.belgium.main.time.sleep", lambda _: None)

    with pytest.raises(requests.Timeout):
        belgium._get("https://example/wfs", {})


def _always_timeout(*args: object, **kwargs: object) -> requests.Response:
    raise requests.Timeout("down")


def test_belgium_main_downloads_each_region_and_writes_both_overlays(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_download(raw_dir: Path) -> None:
        _seed_raw(raw_dir)

    monkeypatch.setattr(belgium, "download_sources", fake_download)

    belgium.main(["--data-dir", str(tmp_path)])

    out = tmp_path / "belgium" / "restrictions"
    assert set(gpd.read_parquet(out / "zepa.parquet")["name"]) == {
        "Zwin", "Lesse et Lomme"}
    assert set(gpd.read_parquet(out / "zec.parquet")["name"]) == {
        "Dijlevallei", "Lesse et Lomme"}


def test_download_sources_covers_both_regions(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fetched: list[str] = []
    monkeypatch.setattr(belgium, "_download_flanders",
                        lambda raw, key, type_name: fetched.append(key))
    monkeypatch.setattr(belgium, "_download_wallonia",
                        lambda raw: fetched.append("wallonia"))

    belgium.download_sources(tmp_path / "raw")

    assert fetched == [*belgium.FLANDERS_PARTS, "wallonia"]


def test_belgium_restriction_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.restriction.belgium.main.main") as entry:
        runpy.run_module("highliner.etls.restriction.belgium.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
