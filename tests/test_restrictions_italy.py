from pathlib import Path

import geopandas as gpd
import pytest
from highliner.etls.restriction import italy, shared
from shapely.geometry import Polygon

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def _n2000_source() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "site_name": ["Birds Only", "Habitat Only", "Both", "Untyped"],
            "site_type": ["A", "B", "C", ""],
        },
        geometry=[_SQUARE, _SQUARE, _SQUARE, _SQUARE],
        crs="EPSG:4326",
    )


def test_build_zps_keeps_spa_and_both() -> None:
    gdf = shared.build_layer(_n2000_source(), italy.SPECS["zps"])
    assert sorted(gdf["name"]) == ["Birds Only", "Both"]
    assert gdf.crs.to_epsg() == 4326


def test_build_zsc_keeps_sci_sac_and_both() -> None:
    gdf = shared.build_layer(_n2000_source(), italy.SPECS["zsc"])
    assert sorted(gdf["name"]) == ["Both", "Habitat Only"]


def test_build_euap_keeps_all_and_normalizes_name() -> None:
    src = gpd.GeoDataFrame(
        {"nome_gazze": ["  Parco  ", None]},
        geometry=[_SQUARE, _SQUARE], crs="EPSG:4326",
    )
    gdf = shared.build_layer(src, italy.SPECS["euap"])
    assert sorted(gdf["name"]) == ["", "Parco"]


def test_load_source_unknown_key_raises(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        italy._load_source("nope", raw_dir=tmp_path)


def test_load_source_n2000_joins_site_database(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base_gdf = gpd.GeoDataFrame(
        {"site_code": ["IT1", "IT2"]}, geometry=[_SQUARE, _SQUARE],
        crs="EPSG:4326")
    monkeypatch.setattr(italy, "_load_files", lambda rd, pats: base_gdf.copy())
    monkeypatch.setattr(italy, "_read_site_db",
                        lambda rd: {"IT1": ("C", "Gran Sasso")})

    gdf = italy._load_source("n2000", raw_dir=tmp_path)

    assert list(gdf["site_type"]) == ["C", ""]
    assert list(gdf["site_name"]) == ["Gran Sasso", ""]


def test_load_files_reprojects_to_wgs84(tmp_path: Path) -> None:
    gpd.GeoDataFrame(
        {"site_code": ["IT1"]}, geometry=[_SQUARE], crs="EPSG:4326"
    ).to_crs(32632).to_file(tmp_path / "sic_zps_x.geojson", driver="GeoJSON")

    gdf = italy._load_files(tmp_path, ("sic_zps_*.geojson",))

    assert gdf.crs.to_epsg() == 4326
    assert list(gdf["site_code"]) == ["IT1"]


def test_read_site_db_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        italy._read_site_db(tmp_path)


def test_write_layers_writes_the_three_layers(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    n2000 = _n2000_source()
    euap = gpd.GeoDataFrame(
        {"nome_gazze": ["Parco"]}, geometry=[_SQUARE], crs="EPSG:4326")
    monkeypatch.setattr(
        italy, "_load_source", lambda key: n2000 if key == "n2000" else euap)

    written = shared.write_layers(italy.SPECS.values(), italy._load_source,
                                  tmp_path / "out")

    assert set(written) == {"zps", "zsc", "euap"}
    for lid in ("zps", "zsc", "euap"):
        assert (tmp_path / "out" / f"{lid}.parquet").exists()


def test_italy_restriction_main_downloads_then_writes(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(italy, "download_sources",
                        lambda raw_dir: calls.append(raw_dir))
    monkeypatch.setattr(italy.shared, "write_layers", lambda *args, **kwargs: {})

    italy.main(["--data-dir", str(tmp_path)])

    assert calls == [tmp_path / "italy" / "restrictions" / "raw"]


def test_download_sources_skips_present_and_saves_plain_files(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "sic_zps_x.shp").write_bytes(b"")     # n2000 already present
    fetched: list[tuple[str, Path]] = []
    monkeypatch.setattr(italy, "_download",
                        lambda url, dest: fetched.append((url, dest)))

    italy.download_sources(tmp_path)

    assert fetched == [
        (italy.SOURCE_URLS["n2000_db"],
         tmp_path / "Italy_database_trasmesso.xlsx"),
        (italy.SOURCE_URLS["euap"], tmp_path / "euap.gml"),
    ]
