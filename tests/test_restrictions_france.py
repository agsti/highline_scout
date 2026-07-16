import json
from pathlib import Path

import geopandas as gpd
import pytest
from highliner.etls.restriction import france, shared
from shapely.geometry import Polygon

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def _patrinat(names: list[str | None],
              **extra: list[object]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"nom_site": names, **extra},
        geometry=[_SQUARE] * len(names), crs="EPSG:4326")


def test_build_fr_zps_keeps_all_and_normalizes_name() -> None:
    gdf = shared.build_layer(_patrinat(["  Gorges du Tarn  ", None]),
                             france.SPECS["fr_zps"])
    assert sorted(gdf["name"]) == ["", "Gorges du Tarn"]
    assert gdf.crs.to_epsg() == 4326


def test_load_source_ep_concatenates_and_keeps_only_park_cores(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frames = {
        ("pn.geojson",): _patrinat(["Ecrins", "Ecrins [Aire D'Adhésion]"],
                                   zone=["Cœur", "Adhesion"]),
        ("rnn.geojson",): _patrinat(["RNN Haute Chaîne du Jura"]),
        ("rnr.geojson",): _patrinat(["RNR Cirque du Fer à Cheval"]),
        ("apb.geojson",): _patrinat(["APPB Falaise du Saussois"]),
    }
    monkeypatch.setattr(france, "_load_files",
                        lambda rd, pats: frames[pats].copy())

    gdf = france._load_source("ep", raw_dir=tmp_path)

    assert sorted(gdf["nom_site"]) == [
        "APPB Falaise du Saussois", "Ecrins",
        "RNN Haute Chaîne du Jura", "RNR Cirque du Fer à Cheval"]
    assert gdf.crs.to_epsg() == 4326


def test_load_source_unknown_key_raises(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        france._load_source("nope", raw_dir=tmp_path)


def test_load_files_reprojects_to_wgs84(tmp_path: Path) -> None:
    _patrinat(["FR1"]).to_crs(2154).to_file(
        tmp_path / "zps.geojson", driver="GeoJSON")

    gdf = france._load_files(tmp_path, ("zps.geojson",))

    assert gdf.crs.to_epsg() == 4326
    assert list(gdf["nom_site"]) == ["FR1"]


def test_load_files_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        france._load_files(tmp_path, ("zps.geojson",))


def test_write_layers_writes_the_three_layers(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    natura = _patrinat(["Site"])
    ep = _patrinat(["Réserve"])
    monkeypatch.setattr(
        france, "_load_source", lambda key: ep if key == "ep" else natura)

    written = shared.write_layers(france.SPECS.values(), france._load_source,
                                  tmp_path / "out")

    assert set(written) == {"fr_zps", "fr_zsc", "fr_ep"}
    for lid in ("fr_zps", "fr_zsc", "fr_ep"):
        assert (tmp_path / "out" / f"{lid}.parquet").exists()


def test_france_restriction_main_downloads_then_writes(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(france, "download_sources",
                        lambda raw_dir: calls.append(raw_dir))
    monkeypatch.setattr(france.shared, "write_layers", lambda *args, **kwargs: {})

    france.main(["--data-dir", str(tmp_path)])

    assert calls == [tmp_path / "france" / "restrictions" / "raw"]


def test_download_sources_skips_present_and_fetches_missing(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "zps.geojson").write_text("{}")     # zps already present
    fetched: list[tuple[str, Path]] = []
    monkeypatch.setattr(france, "_download_wfs",
                        lambda typename, dest: fetched.append((typename, dest)))

    france.download_sources(tmp_path)

    assert fetched == [
        (france.TYPENAMES[key], tmp_path / f"{key}.geojson")
        for key in ("sic", "pn", "rnn", "rnr", "apb")]


def test_download_wfs_pages_until_a_short_page(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pages: dict[int, dict[str, object]] = {
        0: {"features": [{"id": i} for i in range(france._PAGE_SIZE)]},
        france._PAGE_SIZE: {"features": [{"id": "last"}]},
    }
    requested: list[int] = []

    def fake_fetch(typename: str, start: int) -> dict[str, object]:
        requested.append(start)
        return pages[start]

    monkeypatch.setattr(france, "_fetch_page", fake_fetch)
    dest = tmp_path / "zps.geojson"

    france._download_wfs("patrinat_zps:zps", dest)

    assert requested == [0, france._PAGE_SIZE]
    collection = json.loads(dest.read_text())
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == france._PAGE_SIZE + 1
