import io
import runpy
import zipfile
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pytest
import requests
from shapely.geometry import Point

from highliner.core.density import layer_mask


def test_mexico_layer_is_registered_for_density() -> None:
    assert layer_mask(["mx_anp"]) != 0


def test_mexico_load_source_uses_conanp_name(
        tmp_path: Path) -> None:
    from highliner.etls.restriction.mexico import main as mexico
    source = gpd.GeoDataFrame({"NOMBRE": ["  Reserva  "]}, geometry=[Point(-100, 20)],
                              crs="EPSG:4326")
    source.to_file(tmp_path / "anp.shp")

    loaded = mexico._load_source("anp", tmp_path)

    assert list(loaded["NOMBRE"]) == ["Reserva"]


def test_mexico_restriction_main_writes_conanp_layer(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction.mexico import main as mexico
    written: list[set[str]] = []
    monkeypatch.setattr(mexico, "download_sources", lambda _path: None)
    monkeypatch.setattr(
        mexico.shared, "write_layers",
        lambda specs, _load, _dest: written.append({spec.id for spec in specs}))

    mexico.main(["--data-dir", str(tmp_path)])

    assert written == [{"mx_anp"}]


class _FakeArchiveResponse:
    """Streaming stand-in for the CONANP shapefile ZIP `requests.get` returns."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeArchiveResponse":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, _size: int) -> list[bytes]:
        # A keep-alive chunk between the payload blocks: the writer must skip
        # empty blocks rather than write them.
        return [self._payload[:4], b"", self._payload[4:]]


def test_mexico_load_source_rejects_an_unknown_source_key(tmp_path: Path) -> None:
    from highliner.etls.restriction.mexico import main as mexico

    with pytest.raises(KeyError):
        mexico._load_source("not_a_real_source", tmp_path)


def test_mexico_load_source_requires_a_downloaded_shapefile(tmp_path: Path) -> None:
    from highliner.etls.restriction.mexico import main as mexico

    with pytest.raises(FileNotFoundError, match="etl-restriction mexico"):
        mexico._load_source("anp", tmp_path)


def test_mexico_load_source_rejects_a_shapefile_without_a_crs(
        tmp_path: Path) -> None:
    from highliner.etls.restriction.mexico import main as mexico
    # No .prj alongside the shapefile, so GDAL reports no CRS and the layer
    # cannot be reprojected to WGS84.
    gpd.GeoDataFrame({"NOMBRE": ["Reserva"]},
                     geometry=[Point(-100, 20)]).to_file(tmp_path / "anp.shp")
    (tmp_path / "anp.prj").unlink(missing_ok=True)

    with pytest.raises(ValueError, match="no CRS"):
        mexico._load_source("anp", tmp_path)


def test_mexico_download_sources_flattens_the_conanp_archive(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction.mexico import main as mexico
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("nested/", b"")
        zipped.writestr("nested/anp.shp", b"shp")
        zipped.writestr("nested/anp.dbf", b"dbf")
    monkeypatch.setattr(requests, "get", lambda *a, **k:
                        _FakeArchiveResponse(buffer.getvalue()))
    raw_dir = tmp_path / "raw"

    mexico.download_sources(raw_dir)

    assert (raw_dir / "anp.shp").read_bytes() == b"shp"
    assert (raw_dir / "anp.dbf").read_bytes() == b"dbf"
    assert not list(raw_dir.glob("*.zip"))


def test_mexico_download_sources_keeps_an_existing_extraction(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.restriction.mexico import main as mexico

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not re-download an existing source")

    monkeypatch.setattr(requests, "get", boom)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "anp.shp").write_bytes(b"shp")

    mexico.download_sources(raw_dir)

    assert (raw_dir / "anp.shp").read_bytes() == b"shp"


def test_mexico_restriction_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.restriction.mexico.main.main") as entry:
        runpy.run_module("highliner.etls.restriction.mexico.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
