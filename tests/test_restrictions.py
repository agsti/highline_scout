from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from highliner.etls.restriction import shared, spain
from highliner.server.repositories.restrictions import load_layer

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def _write(path: Path, epsg: int, name: str) -> None:
    gpd.GeoDataFrame(
        {"SITE_NAME": [name]}, geometry=[_SQUARE], crs="EPSG:4326"
    ).to_crs(epsg).to_file(path, driver="GeoJSON")


def test_load_files_concats_and_reprojects(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _write(raw / "enp_p.json", 25830, "Peninsula")
    _write(raw / "enp_c.json", 32628, "Canarias")

    gdf = spain._load_files(raw, ("*.geojson", "*.json"))

    assert gdf.crs.to_epsg() == 4326
    assert sorted(gdf["SITE_NAME"]) == ["Canarias", "Peninsula"]


def test_load_files_missing_raises(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    with pytest.raises(FileNotFoundError):
        spain._load_files(raw, ("*.gml",))


_GML = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection
    xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns:gml="http://www.opengis.net/gml/3.2"
    xmlns:ps="http://inspire.ec.europa.eu/schemas/ps/5.0"
    xmlns:base="http://inspire.ec.europa.eu/schemas/base/4.0"
    xmlns:xlink="http://www.w3.org/1999/xlink">
  <wfs:member>
    <ps:ProtectedSite>
      <ps:inspireId><base:Identifier><base:localId>ES0000197</base:localId></base:Identifier></ps:inspireId>
      <ps:siteDesignation><ps:DesignationType>
        <ps:designation xlink:href="http://inspire.ec.europa.eu/codelist/Natura2000DesignationValue/SpecialProtecionArea"/>
      </ps:DesignationType></ps:siteDesignation>
    </ps:ProtectedSite>
  </wfs:member>
  <wfs:member>
    <ps:ProtectedSite>
      <ps:inspireId><base:Identifier><base:localId>ES6300001</base:localId></base:Identifier></ps:inspireId>
      <ps:siteDesignation><ps:DesignationType>
        <ps:designation xlink:href="http://inspire.ec.europa.eu/codelist/Natura2000DesignationValue/SiteOfCommunityImportance"/>
      </ps:DesignationType></ps:siteDesignation>
      <ps:siteDesignation><ps:DesignationType>
        <ps:designation xlink:href="http://inspire.ec.europa.eu/codelist/Natura2000DesignationValue/SpecialProtectionArea"/>
      </ps:DesignationType></ps:siteDesignation>
    </ps:ProtectedSite>
  </wfs:member>
</wfs:FeatureCollection>
"""


def test_parse_designations(tmp_path: Path) -> None:
    gml = tmp_path / "rn.gml"
    gml.write_text(_GML)

    codes = spain._parse_designations(gml)

    assert codes["ES0000197"] == {"SpecialProtecionArea"}          # typo-only ZEPA
    assert codes["ES6300001"] == {"SiteOfCommunityImportance", "SpecialProtectionArea"}


def _rn2000_source() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "text": ["Birds Only", "Habitat Only", "Both"],
            "designations": [
                {"SpecialProtecionArea"},                       # typo ZEPA
                {"SiteOfCommunityImportance"},                  # ZEC
                {"SpecialProtectionArea", "SpecialAreaOfConservation"},
            ],
        },
        geometry=[_SQUARE, _SQUARE, _SQUARE],
        crs="EPSG:4326",
    )


def test_build_zepa_keeps_spa_incl_typo_and_both() -> None:
    gdf = shared.build_layer(_rn2000_source(), spain.SPECS["zepa"])
    assert sorted(gdf["name"]) == ["Birds Only", "Both"]
    assert gdf.crs.to_epsg() == 4326


def test_build_zec_keeps_sci_sac_and_both() -> None:
    gdf = shared.build_layer(_rn2000_source(), spain.SPECS["zec"])
    assert sorted(gdf["name"]) == ["Both", "Habitat Only"]


def test_build_enp_keeps_all_and_normalizes_name() -> None:
    src = gpd.GeoDataFrame(
        {"SITE_NAME": ["  Park  ", None]},
        geometry=[_SQUARE, _SQUARE], crs="EPSG:4326",
    )
    gdf = shared.build_layer(src, spain.SPECS["enp"])
    assert sorted(gdf["name"]) == ["", "Park"]


def test_build_layer_empty_source_returns_empty() -> None:
    src = gpd.GeoDataFrame(
        {"text": [], "designations": []}, geometry=[], crs="EPSG:4326")
    gdf = shared.build_layer(src, spain.SPECS["zepa"])
    assert len(gdf) == 0
    assert gdf.crs.to_epsg() == 4326


def test_load_source_unknown_key_raises(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        spain._load_source("nope", raw_dir=tmp_path)


def test_load_source_rn2000_attaches_designations(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "x.gml").write_text("<x/>")  # so base.glob("*.gml") finds a file
    base_gdf = gpd.GeoDataFrame(
        {"localId": ["ES1", "ES2"]}, geometry=[_SQUARE, _SQUARE], crs="EPSG:4326")
    monkeypatch.setattr(spain, "_load_files", lambda rd, pats: base_gdf.copy())
    monkeypatch.setattr(spain, "_parse_designations",
                        lambda p: {"ES1": {"SpecialProtectionArea"}})

    gdf = spain._load_source("rn2000", raw_dir=raw)

    assert list(gdf["designations"]) == [{"SpecialProtectionArea"}, set()]


def test_write_layers_writes_the_three_layers(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rn = _rn2000_source()
    enp = gpd.GeoDataFrame(
        {"SITE_NAME": ["Park"]}, geometry=[_SQUARE], crs="EPSG:4326")
    monkeypatch.setattr(
        spain, "_load_source", lambda key: rn if key == "rn2000" else enp)

    written = shared.write_layers(spain.SPECS.values(), spain._load_source,
                                  tmp_path / "out")

    assert set(written) == {"zepa", "zec", "enp"}
    for lid in ("zepa", "zec", "enp"):
        assert (tmp_path / "out" / f"{lid}.parquet").exists()
    assert len(load_layer(str(tmp_path / "out" / "enp.parquet"))) == 1


def test_spain_restriction_main_downloads_then_writes(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(spain, "download_sources",
                        lambda raw_dir: calls.append(raw_dir))
    monkeypatch.setattr(spain.shared, "write_layers", lambda *args, **kwargs: {})

    spain.main(["--data-dir", str(tmp_path)])

    assert calls == [tmp_path / "spain" / "restrictions" / "raw"]


def test_download_sources_fetches_missing_and_skips_present(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Regression: raw_dir.glob() returns generators, which are truthy even
    # when empty — a bare any(...) skipped every download on a fresh checkout.
    (tmp_path / "enp_x.geojson").write_bytes(b"")     # enp already present
    fetched: list[str] = []

    def fake_urlretrieve(url: str, dest: Path) -> None:
        fetched.append(url)
        dest.write_bytes(b"zip")

    monkeypatch.setattr(spain, "urlretrieve", fake_urlretrieve)
    monkeypatch.setattr(spain, "_extract_flattened",
                        lambda archive, dest_dir: None)

    spain.download_sources(tmp_path)

    assert fetched == [spain.SOURCE_URLS["rn2000"]]
