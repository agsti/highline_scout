from pathlib import Path

import pytest
import requests

from highliner.etls.chunk.belgium import dtm_dhmv


def _response(status: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def _multipart(tiff: bytes) -> bytes:
    return (b"--wcs\r\nContent-Type: text/xml\r\n\r\n<coverage/>\r\n"
            b"--wcs\r\nContent-Type: image/tiff\r\nContent-ID: 1.tif\n\n"
            + tiff + b"\n--wcs--\r\n")


def test_tiff_body_extracts_the_attachment_from_the_multipart_envelope() -> None:
    assert dtm_dhmv._tiff_body(_multipart(b"II*\x00fake")) == b"II*\x00fake"


def test_tiff_body_rejects_a_response_without_a_geotiff_part() -> None:
    with pytest.raises(RuntimeError, match="no GeoTIFF attachment"):
        dtm_dhmv._tiff_body(b"--wcs\r\nContent-Type: text/xml\r\n\r\n<error/>")


def test_tiff_body_rejects_a_part_whose_headers_never_end() -> None:
    with pytest.raises(RuntimeError, match="invalid GeoTIFF attachment"):
        dtm_dhmv._tiff_body(b"Content-ID: 1.tif\r\nContent-Type: image/tiff")


def test_tiff_body_rejects_an_unterminated_geotiff_part() -> None:
    with pytest.raises(RuntimeError, match="unterminated GeoTIFF"):
        dtm_dhmv._tiff_body(b"Content-ID: 1.tif\n\nII*\x00truncated")


def test_fetch_dhmv_writes_the_geotiff_and_asks_for_5m(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return _response(200, _multipart(b"II*\x00fake-geotiff"))

    monkeypatch.setattr(requests, "get", fake_get)

    paths = dtm_dhmv.fetch_dhmv((100, 200, 110, 210), tmp_path, "EPSG:31370")

    assert paths == [tmp_path / "t_100_200.tif"]
    assert paths[0].read_bytes() == b"II*\x00fake-geotiff"
    assert calls[0]["coverageId"] == "DHMVII_DTM_1m"
    # The source is 1 m; 0.2 is what resamples it to the pipeline's 5 m grid.
    assert calls[0]["scalefactor"] == "0.2"
    assert calls[0]["subset"] == ["x(100,110)", "y(200,210)"]


def test_fetch_dhmv_raises_for_an_http_error(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _response(404, b"missing"))
    with pytest.raises(requests.HTTPError):
        dtm_dhmv.fetch_dhmv((0, 0, 1, 1), tmp_path, "EPSG:31370")


def test_fetch_dhmv_rejects_a_non_national_crs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EPSG:31370"):
        dtm_dhmv.fetch_dhmv((0, 0, 1, 1), tmp_path, "EPSG:4326")


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

    paths = dtm_dhmv.fetch((100, 200, 110, 210), tmp_path, None, "EPSG:31370")

    assert len(paths) == 1
    assert attempts == 2


def test_belgium_fetch_ignores_cache_dir_and_forwards_the_rest(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, tiles_dir: object, crs: object) -> list[Path]:
        seen.append((bbox, tiles_dir, crs))
        return []

    monkeypatch.setattr(dtm_dhmv, "fetch_dhmv", fake)
    dtm_dhmv.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", tmp_path / "cache",
                   "EPSG:31370")

    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", "EPSG:31370")]
