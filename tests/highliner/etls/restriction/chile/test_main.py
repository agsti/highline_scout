"""Tests for Chile's protected-area adapter."""

import zipfile
from collections.abc import Iterable
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from highliner.core.restrictions import LAYERS
from highliner.etls.restriction import shared

_SQUARE = Polygon([(-70.0, -33.0), (-70.0, -32.9),
                   (-69.9, -32.9), (-69.9, -33.0)])


def _source(designation: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"nombre_ap": ["  Parque de Prueba  "], "designacion_ap": [designation]},
        geometry=[_SQUARE], crs="EPSG:4326")


def test_chile_specs_build_three_named_layers_by_designation() -> None:
    from highliner.etls.restriction.chile import main as chile

    assert set(chile.SPECS) == {
        "cl_snaspe", "cl_santuario", "cl_conservacion_privada",
    }

    snaspe = shared.build_layer(_source("Parque Nacional"),
                                chile.SPECS["cl_snaspe"])
    assert list(snaspe["name"]) == ["Parque de Prueba"]

    santuario = shared.build_layer(_source("Santuario de la Naturaleza"),
                                   chile.SPECS["cl_santuario"])
    assert list(santuario["name"]) == ["Parque de Prueba"]

    privada = shared.build_layer(_source("Conservación Privada y Comunitaria"),
                                 chile.SPECS["cl_conservacion_privada"])
    assert list(privada["name"]) == ["Parque de Prueba"]


def test_chile_specs_exclude_marine_designations() -> None:
    from highliner.etls.restriction.chile import main as chile

    marine = _source("Parque Marino")
    for spec in chile.SPECS.values():
        assert len(shared.build_layer(marine, spec)) == 0


def test_load_source_reprojects_to_wgs84(tmp_path: Path) -> None:
    from highliner.etls.restriction.chile import main as chile

    projected = _source("Parque Nacional").to_crs("EPSG:32719")
    projected.to_file(tmp_path / "areas-protegidas.geojson", driver="GeoJSON")

    loaded = chile._load_source("areas_protegidas", tmp_path)

    assert loaded.crs.to_epsg() == 4326
    assert list(loaded["nombre_ap"]) == ["  Parque de Prueba  "]


def test_load_source_rejects_unknown_key(tmp_path: Path) -> None:
    from highliner.etls.restriction.chile import main as chile

    with pytest.raises(KeyError):
        chile._load_source("not_a_real_source", tmp_path)


def test_load_source_requires_a_downloaded_file(tmp_path: Path) -> None:
    from highliner.etls.restriction.chile import main as chile

    with pytest.raises(FileNotFoundError, match="etl-restriction chile"):
        chile._load_source("areas_protegidas", tmp_path)


def test_has_source_and_extract_flattened(tmp_path: Path) -> None:
    from highliner.etls.restriction.chile import main as chile

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    assert not chile._has_source(raw_dir)

    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("nested/areas-protegidas.geojson", b"{}")

    chile._extract_flattened(archive_path, raw_dir)

    assert (raw_dir / "areas-protegidas.geojson").read_bytes() == b"{}"
    assert chile._has_source(raw_dir)


def test_download_sources_skips_when_already_present(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.restriction.chile import main as chile

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "areas-protegidas.geojson").write_text("{}")

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not re-download an existing source")

    monkeypatch.setattr(chile, "_download", boom)

    chile.download_sources(raw_dir)


def test_download_sources_fetches_and_flattens_when_missing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.restriction.chile import main as chile

    raw_dir = tmp_path / "raw"

    def fake_download(_url: str, dest: Path) -> None:
        with zipfile.ZipFile(dest, "w") as archive:
            archive.writestr("areas-protegidas.geojson",
                             b'{"type":"FeatureCollection"}')

    monkeypatch.setattr(chile, "_download", fake_download)

    chile.download_sources(raw_dir)

    assert (raw_dir / "areas-protegidas.geojson").exists()
    assert not list(raw_dir.glob("*.zip"))


def test_restriction_main_downloads_then_writes(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction.chile import main as chile

    downloaded: list[Path] = []
    written: list[tuple[set[str], Path]] = []

    def fake_write(specs: Iterable[shared.LayerBuildSpec], _loader: object,
                   dest: Path) -> dict[str, Path]:
        written.append(({spec.id for spec in specs}, dest))
        return {}

    monkeypatch.setattr(chile, "download_sources",
                        lambda raw_dir: downloaded.append(raw_dir))
    monkeypatch.setattr(chile.shared, "write_layers", fake_write)

    chile.main(["--data-dir", str(tmp_path)])

    restrictions = tmp_path / "chile" / "restrictions"
    assert downloaded == [restrictions / "raw"]
    assert written == [({
        "cl_snaspe", "cl_santuario", "cl_conservacion_privada",
    }, restrictions)]


def test_chile_layer_metadata_highlights_rigging_impact() -> None:
    for layer_id in ("cl_snaspe", "cl_santuario", "cl_conservacion_privada"):
        spec = LAYERS[layer_id]
        assert spec["highlight"] in spec["tooltip"]
        assert "rigging" in spec["highlight"].lower()
