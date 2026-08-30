from pathlib import Path

import pytest
import requests

from highliner.etls.chunk.belgium import dtm_dhmv

# A chunk-sized halo bbox wholly inside the DHMV coverage envelope.
INSIDE = (60_000.0, 160_000.0, 72_100.0, 172_100.0)


def _response(status: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def _multipart(tiff: bytes) -> bytes:
    return (b"--wcs\r\nContent-Type: text/xml\r\n\r\n<coverage/>\r\n"
            b"--wcs\r\nContent-Type: image/tiff\r\nContent-ID: 1.tif\n\n"
            + tiff + b"\n--wcs--\r\n")


_EXTENT_ERROR = (b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/2.0">'
                 b'<ows:Exception exceptionCode="InvalidSubsetting"/>'
                 b'</ows:ExceptionReport>')
_NO_DATA_ERROR = (b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/2.0">'
                  b'<ows:Exception exceptionCode="Failed to get coverage data"/>'
                  b'</ows:ExceptionReport>')


def test_tiff_body_extracts_the_attachment_from_the_multipart_envelope() -> None:
    assert dtm_dhmv._tiff_body(_multipart(b"II*\x00fake")) == b"II*\x00fake"


def test_tiff_body_keeps_raster_bytes_that_spell_the_part_boundary() -> None:
    raster = b"II*\x00" + b"\n--wcs" + b"\xff\xfe"
    assert dtm_dhmv._tiff_body(_multipart(raster)) == raster


def test_tiff_body_rejects_a_response_without_a_geotiff_part() -> None:
    with pytest.raises(RuntimeError, match="no GeoTIFF attachment"):
        dtm_dhmv._tiff_body(b"--wcs\r\nContent-Type: text/xml\r\n\r\n<error/>")


def test_tiff_body_rejects_a_part_whose_headers_never_end() -> None:
    with pytest.raises(RuntimeError, match="invalid GeoTIFF attachment"):
        dtm_dhmv._tiff_body(b"Content-ID: 1.tif\r\nContent-Type: image/tiff")


def test_tiff_body_rejects_an_unterminated_geotiff_part() -> None:
    with pytest.raises(RuntimeError, match="unterminated GeoTIFF"):
        dtm_dhmv._tiff_body(b"Content-ID: 1.tif\n\nII*\x00truncated")


def test_tiff_body_reports_an_ows_exception_served_as_the_raster() -> None:
    with pytest.raises(RuntimeError, match="Failed to get coverage data"):
        dtm_dhmv._tiff_body(_multipart(_NO_DATA_ERROR))


def test_tiff_body_reports_an_unparseable_payload_served_as_the_raster() -> None:
    with pytest.raises(RuntimeError, match="unrecognised payload"):
        dtm_dhmv._tiff_body(_multipart(b"not xml and not a tiff"))


def test_tiff_body_reports_a_report_carrying_no_exception_code() -> None:
    with pytest.raises(RuntimeError, match="no exceptionCode"):
        dtm_dhmv._tiff_body(_multipart(b"<ExceptionReport/>"))


def test_fetch_dhmv_writes_the_geotiff_and_pins_the_5m_grid(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return _response(200, _multipart(b"II*\x00fake-geotiff"))

    monkeypatch.setattr(requests, "get", fake_get)

    paths = dtm_dhmv.fetch_dhmv(INSIDE, tmp_path, "EPSG:31370")

    assert paths == [tmp_path / "t_60000_160000.tif"]
    assert paths[0].read_bytes() == b"II*\x00fake-geotiff"
    assert calls[0]["coverageId"] == "DHMVII_DTM_1m"
    # scalefactor is applied inverted by this server; scalesize pins 12100 m
    # of Lambert 72 onto the pipeline's 5 m grid exactly.
    assert "scalefactor" not in calls[0]
    assert calls[0]["scalesize"] == "x(2420),y(2420)"
    assert calls[0]["subset"] == ["x(60000.0,72100.0)", "y(160000.0,172100.0)"]


def test_fetch_dhmv_clips_a_halo_that_overhangs_the_coverage_envelope(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return _response(200, _multipart(b"II*\x00fake-geotiff"))

    monkeypatch.setattr(requests, "get", fake_get)

    # The bottom-left chunk of `flanders`: its halo hangs below y=148000.
    dtm_dhmv.fetch_dhmv((15_950.0, 146_950.0, 28_050.0, 159_050.0),
                        tmp_path, "EPSG:31370")

    assert calls[0]["subset"] == ["x(17000.0,28050.0)", "y(148000.0,159050.0)"]
    assert calls[0]["scalesize"] == "x(2210),y(2210)"


def test_fetch_dhmv_skips_a_bbox_entirely_outside_the_coverage(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get", _unreachable_get)

    assert dtm_dhmv.fetch_dhmv((0.0, 0.0, 1_000.0, 1_000.0), tmp_path,
                               "EPSG:31370") == []


def _unreachable_get(*args: object, **kwargs: object) -> requests.Response:
    raise AssertionError("no request should be issued outside the coverage")


def test_fetch_dhmv_treats_an_invalid_subsetting_reply_as_no_coverage(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _response(404, _EXTENT_ERROR))

    assert dtm_dhmv.fetch_dhmv(INSIDE, tmp_path, "EPSG:31370") == []


def test_fetch_dhmv_raises_for_an_http_error(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _response(500, b"boom"))
    with pytest.raises(requests.HTTPError):
        dtm_dhmv.fetch_dhmv(INSIDE, tmp_path, "EPSG:31370")


def test_fetch_dhmv_rejects_a_non_national_crs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EPSG:31370"):
        dtm_dhmv.fetch_dhmv(INSIDE, tmp_path, "EPSG:4326")


def test_belgium_fetch_retries_a_transient_wcs_failure(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    attempts = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.Timeout("temporary timeout")
        return _response(200, _multipart(b"II*\x00fake-geotiff"))

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda _: None)

    paths = dtm_dhmv.fetch(INSIDE, tmp_path, None, "EPSG:31370")

    assert len(paths) == 1
    assert attempts == 2


def test_belgium_fetch_ignores_cache_dir_and_forwards_the_rest(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, tiles_dir: object, crs: object) -> list[Path]:
        seen.append((bbox, tiles_dir, crs))
        return []

    monkeypatch.setattr(dtm_dhmv, "fetch_dhmv", fake)
    dtm_dhmv.fetch(INSIDE, tmp_path / "tiles", tmp_path / "cache",
                   "EPSG:31370")

    assert seen == [(INSIDE, tmp_path / "tiles", "EPSG:31370")]


_ARCGIS_400 = (b"<html><body><h1>Error occurred while processing request"
               b"</h1></body></html>")


def test_fetch_dhmv_retries_the_arcgis_backend_error_page(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    replies = [_response(400, _ARCGIS_400), _response(400, _ARCGIS_400),
               _response(200, _multipart(b"II*\x00fake-geotiff"))]
    monkeypatch.setattr(requests, "get", lambda *a, **k: replies.pop(0))
    monkeypatch.setattr(
        "highliner.etls.chunk.belgium.dtm_dhmv.time.sleep", lambda _: None)

    assert dtm_dhmv.fetch_dhmv(INSIDE, tmp_path, "EPSG:31370") == [
        tmp_path / "t_60000_160000.tif"]
    assert replies == []


def test_fetch_dhmv_gives_up_on_a_persistent_arcgis_backend_error(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    attempts = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal attempts
        attempts += 1
        return _response(400, _ARCGIS_400)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(
        "highliner.etls.chunk.belgium.dtm_dhmv.time.sleep", lambda _: None)

    with pytest.raises(requests.HTTPError):
        dtm_dhmv.fetch_dhmv(INSIDE, tmp_path, "EPSG:31370")
    assert attempts == dtm_dhmv.ARCGIS_RETRIES


def test_fetch_dhmv_does_not_retry_an_extent_error_sent_as_400(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    attempts = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal attempts
        attempts += 1
        return _response(400, _EXTENT_ERROR)

    monkeypatch.setattr(requests, "get", fake_get)

    assert dtm_dhmv.fetch_dhmv(INSIDE, tmp_path, "EPSG:31370") == []
    assert attempts == 1
