import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
import rasterio
import requests

from highliner.etls.chunk.dtm_core import NODATA
from highliner.etls.chunk.mexico import dtm_inegi


def test_sheet_keys_for_bbox_selects_catalogue_centres_inside_expanded_bbox() -> None:
    catalogue = [
        {"cve": "OUTSIDE", "x": 0, "y": 0},
        {"cve": "INSIDE", "x": -11000000, "y": 2200000},
    ]

    assert dtm_inegi._sheet_keys_for_bbox(
        catalogue, (-11001000, 2199000, -10999000, 2201000), "EPSG:3857") == [
            "INSIDE"]


def test_archive_url_uses_latest_terrain_ascii_record() -> None:
    records = [
        {"url_descarga": "https://example.test/new", "archivo": "_as.zip, 1 MB"},
        {"url_descarga": "https://example.test/old", "archivo": "_as.zip, 1 MB"},
    ]

    assert dtm_inegi._archive_url(records) == "https://example.test/new_as.zip"


def test_fetch_reuses_cached_extracted_sheet(
        tmp_path: Path, monkeypatch: Any) -> None:
    cache_dir = tmp_path / "cache"
    cached = cache_dir / "inegi_mdt5" / "F13D19A1.tif"
    cached.parent.mkdir(parents=True)
    cached.write_text("ncols 1\nnrows 1\nNODATA_value -9999\n0\n")
    monkeypatch.setattr(dtm_inegi, "_catalogue", lambda: [
        {"cve": "F13D19A1", "x": -11000000, "y": 2200000}])
    monkeypatch.setattr(dtm_inegi, "_sheet_keys_for_bbox",
                        lambda _catalogue, _bbox, _crs: ["F13D19A1"])
    monkeypatch.setattr(dtm_inegi, "_reproject", lambda source, dest, _crs: dest)

    paths = dtm_inegi.fetch(
        (-11001000, 2199000, -10999000, 2201000), tmp_path / "tiles",
        cache_dir, "EPSG:3857")

    assert paths == [tmp_path / "tiles" / "F13D19A1.tif"]


class _FakeJsonResponse:
    """Minimal stand-in for the JSON POSTs INEGI's catalogue endpoints answer."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> Any:
        return self._payload


class _FakeArchiveResponse:
    """Streaming stand-in for the ZIP `requests.get` returns for a sheet."""

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


_METADATA = "Número de zona UTM: 14\n".encode("latin-1")
# A 2x2 grid of 5 m posts, in the XYZ order INEGI exports (south-up rows).
_XYZ = b"\n".join([
    b"400000.0 2200000.0 11.0",
    b"400005.0 2200000.0 12.0",
    b"400000.0 2200005.0 13.0",
    b"400005.0 2200005.0 14.0",
])


def _sheet_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("F14D19A1.xyz", _XYZ)
        zipped.writestr("F14D19A1_mt.txt", _METADATA)
    return buffer.getvalue()


def test_catalogue_asks_only_for_5m_terrain_sheets(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeJsonResponse:
        seen.update({"url": url, **kwargs})
        return _FakeJsonResponse([{"cve": "F14D19A1", "x": 0, "y": 0}])

    monkeypatch.setattr(requests, "post", fake_post)

    assert dtm_inegi._catalogue() == [{"cve": "F14D19A1", "x": 0, "y": 0}]
    assert seen["url"] == dtm_inegi.CATALOGUE_URL
    assert seen["data"] == {"res": "5", "mod": "T"}


def test_archive_url_rejects_a_sheet_without_an_ascii_archive() -> None:
    with pytest.raises(RuntimeError, match="ASCII terrain archive"):
        dtm_inegi._archive_url([{"url_descarga": "https://example.test/x",
                                 "archivo": "F14D19A1.tif, 1 MB"}])


def test_write_xyz_grid_georeferences_the_export_in_its_own_utm_zone(
        tmp_path: Path) -> None:
    dest = tmp_path / "F14D19A1.tif"

    dtm_inegi._write_xyz_grid(_XYZ, _METADATA, dest)

    with rasterio.open(dest) as raster:
        # Zone 14 -> Mexico ITRF2008 / UTM zone 14N.
        assert raster.crs.to_epsg() == 6369
        assert raster.res == (5.0, 5.0)
        # Row 0 is the northernmost line of posts, so the y=2200005 pair.
        assert raster.read(1).tolist() == [[13.0, 14.0], [11.0, 12.0]]
        assert raster.bounds.left == pytest.approx(399997.5)
        assert raster.bounds.top == pytest.approx(2200007.5)


def test_write_xyz_grid_rejects_metadata_without_a_utm_zone(
        tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="UTM zone"):
        dtm_inegi._write_xyz_grid(_XYZ, b"Sin zona\n", tmp_path / "x.tif")


def test_download_sheet_converts_the_ascii_archive_and_drops_the_zip(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "post", lambda *a, **k:
                        _FakeJsonResponse([{"url_descarga": "https://example.test/s",
                                            "archivo": "F14D19A1_as.zip, 1 MB"}]))
    monkeypatch.setattr(requests, "get", lambda *a, **k:
                        _FakeArchiveResponse(_sheet_archive()))
    dest = tmp_path / "F14D19A1.tif"

    dtm_inegi._download_sheet("F14D19A1", dest)

    with rasterio.open(dest) as raster:
        assert raster.crs.to_epsg() == 6369
    assert not list(tmp_path.glob("*.zip"))


def test_download_sheet_reports_a_key_the_catalogue_does_not_carry(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "post",
                        lambda *a, **k: _FakeJsonResponse([]))

    with pytest.raises(RuntimeError, match="no 5 m terrain sheet for NOPE"):
        dtm_inegi._download_sheet("NOPE", tmp_path / "NOPE.tif")


def test_download_sheet_rejects_an_archive_missing_its_xyz_or_metadata(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("F14D19A1.xyz", _XYZ)
    monkeypatch.setattr(requests, "post", lambda *a, **k:
                        _FakeJsonResponse([{"url_descarga": "https://example.test/s",
                                            "archivo": "F14D19A1_as.zip, 1 MB"}]))
    monkeypatch.setattr(requests, "get", lambda *a, **k:
                        _FakeArchiveResponse(buffer.getvalue()))

    with pytest.raises(RuntimeError, match="lacks XYZ metadata"):
        dtm_inegi._download_sheet("F14D19A1", tmp_path / "F14D19A1.tif")


def test_reproject_resamples_a_sheet_into_the_region_crs(tmp_path: Path) -> None:
    source = tmp_path / "F14D19A1.tif"
    dtm_inegi._write_xyz_grid(_XYZ, _METADATA, source)

    out = dtm_inegi._reproject(source, tmp_path / "out.tif", "EPSG:6372")

    with rasterio.open(out) as raster:
        assert raster.crs.to_epsg() == 6372
        assert raster.res == (5.0, 5.0)
        assert raster.nodata == NODATA


def test_fetch_downloads_a_sheet_missing_from_the_cache(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    downloaded: list[str] = []

    def fake_download(key: str, dest: Path) -> None:
        downloaded.append(key)
        dtm_inegi._write_xyz_grid(_XYZ, _METADATA, dest)

    monkeypatch.setattr(dtm_inegi, "_download_sheet", fake_download)
    monkeypatch.setattr(dtm_inegi, "_catalogue",
                        lambda: [{"cve": "F14D19A1", "x": -11000000, "y": 2200000}])

    paths = dtm_inegi.fetch((-11001000, 2199000, -10999000, 2201000),
                            tmp_path / "tiles", tmp_path / "cache", "EPSG:3857")

    assert downloaded == ["F14D19A1"]
    assert paths == [tmp_path / "tiles" / "F14D19A1.tif"]
    with rasterio.open(paths[0]) as raster:
        assert raster.crs.to_epsg() == 3857


def test_fetch_requires_a_cache_dir_for_the_shared_sheet_store(
        tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cache_dir"):
        dtm_inegi.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                        "EPSG:6372")


# The variant archive layout: Windows separators, a "_mt_ntm" metadata member
# that is XML despite its .txt name, and the zone as an element.
_VARIANT_METADATA = b"<idinfo><utm><utm_zone>15</utm_zone><utm_longcm>-099.0</utm_longcm></utm></idinfo>"  # noqa: E501


def _variant_sheet_archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("conjunto_de_datos\\d15b63d1_mt.xyz", _XYZ)
        zipped.writestr("metadatos\\d15b63d1_mt_ntm.txt", _VARIANT_METADATA)
        zipped.writestr("metadatos\\metadato_mdt.txt", b"generic product metadata\n")
    return buffer.getvalue()


@pytest.mark.parametrize("name", [
    "metadatos/d14b15b1_mt.txt",
    "metadatos\\d15b63d1_mt_ntm.txt",
    "metadatos\\f14b33d3_mt_ntm_a.txt",
])
def test_member_matches_both_metadata_layouts(name: str) -> None:
    names = ["metadatos/metadato_mdt.txt", "metadatos/x_mt.xml", name]

    assert dtm_inegi._member(names, dtm_inegi._METADATA_MEMBER) == name


def test_member_never_picks_the_generic_product_metadata() -> None:
    assert dtm_inegi._member(["metadatos\\metadato_mdt.txt"],
                             dtm_inegi._METADATA_MEMBER) is None


def test_utm_zone_reads_the_xml_metadata_dialect() -> None:
    assert dtm_inegi._utm_zone(_VARIANT_METADATA) == 15


def test_download_sheet_converts_the_variant_archive_layout(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "post", lambda *a, **k:
                        _FakeJsonResponse([{"url_descarga": "https://example.test/s",
                                            "archivo": "D15B63D1_as.zip, 5 MB"}]))
    monkeypatch.setattr(requests, "get", lambda *a, **k:
                        _FakeArchiveResponse(_variant_sheet_archive()))
    dest = tmp_path / "D15B63D1.tif"

    dtm_inegi._download_sheet("D15B63D1", dest)

    with rasterio.open(dest) as raster:
        # Zone 15 -> Mexico ITRF2008 / UTM zone 15N.
        assert raster.crs.to_epsg() == 6370
    assert not list(tmp_path.glob("*.zip"))


def test_download_sheet_drops_the_zip_when_the_conversion_fails(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("conjunto_de_datos/x.xyz", _XYZ)
    monkeypatch.setattr(requests, "post", lambda *a, **k:
                        _FakeJsonResponse([{"url_descarga": "https://example.test/s",
                                            "archivo": "F14D19A1_as.zip, 1 MB"}]))
    monkeypatch.setattr(requests, "get", lambda *a, **k:
                        _FakeArchiveResponse(buffer.getvalue()))

    with pytest.raises(RuntimeError, match="lacks XYZ metadata"):
        dtm_inegi._download_sheet("F14D19A1", tmp_path / "F14D19A1.tif")

    # The persistent cache must not keep the multi-MB download around.
    assert not list(tmp_path.glob("*.zip"))


def test_fetch_skips_a_sheet_the_source_publishes_no_archive_for(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_download(key: str, dest: Path) -> None:
        if key == "GAP":
            raise dtm_inegi.SheetUnavailable("INEGI catalogue has no ASCII archive")
        dtm_inegi._write_xyz_grid(_XYZ, _METADATA, dest)

    monkeypatch.setattr(dtm_inegi, "_download_sheet", fake_download)
    monkeypatch.setattr(dtm_inegi, "_catalogue", lambda: [
        {"cve": "GAP", "x": -11000000, "y": 2200000},
        {"cve": "F14D19A1", "x": -11000000, "y": 2200000}])

    paths = dtm_inegi.fetch((-11001000, 2199000, -10999000, 2201000),
                            tmp_path / "tiles", tmp_path / "cache", "EPSG:3857")

    assert paths == [tmp_path / "tiles" / "F14D19A1.tif"]
