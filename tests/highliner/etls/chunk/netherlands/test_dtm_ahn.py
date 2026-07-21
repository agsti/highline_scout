from pathlib import Path

import pytest
import requests

from highliner.etls.chunk.netherlands import dtm_ahn


def _response(status: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def test_fetch_ahn_wcs_writes_geotiff_and_scales_to_5m(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return _response(200, b"II*\x00fake-geotiff")

    monkeypatch.setattr(requests, "get", fake_get)

    paths = dtm_ahn.fetch_ahn_wcs((100, 200, 110, 210), tmp_path, "EPSG:28992")

    assert paths == [tmp_path / "t_100_200.tif"]
    assert paths[0].read_bytes() == b"II*\x00fake-geotiff"
    assert calls[0]["scalefactor"] == "0.1"
    assert calls[0]["coverageId"] == "dtm_05m"
    assert calls[0]["subset"] == ["x(100,110)", "y(200,210)"]


def test_fetch_ahn_wcs_treats_extent_error_as_empty(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    content = (
        b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/2.0">'
        b'<ows:Exception exceptionCode="ExtentError" locator="extent">'
        b"<ows:ExceptionText>Image extent does not intersect</ows:ExceptionText>"
        b"</ows:Exception></ows:ExceptionReport>"
    )
    monkeypatch.setattr(requests, "get",
                        lambda *args, **kwargs: _response(400, content))

    assert dtm_ahn.fetch_ahn_wcs(
        (0, 300_000, 5_000, 305_000), tmp_path, "EPSG:28992") == []


def test_netherlands_fetch_does_not_retry_unrelated_bad_request(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    content = (
        b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/2.0">'
        b'<ows:Exception exceptionCode="InvalidParameterValue"/>'
        b"</ows:ExceptionReport>"
    )
    attempts = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal attempts
        attempts += 1
        return _response(400, content)

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(requests.HTTPError):
        dtm_ahn.fetch((100, 200, 110, 210), tmp_path, None, "EPSG:28992")
    assert attempts == 1


def test_netherlands_fetch_retries_transient_wcs_failure(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    attempts = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.Timeout("temporary timeout")
        return _response(200, b"II*\x00fake-geotiff")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda _: None)

    paths = dtm_ahn.fetch((100, 200, 110, 210), tmp_path, None, "EPSG:28992")

    assert len(paths) == 1
    assert attempts == 2


def test_fetch_ahn_wcs_rejects_a_non_national_crs(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="EPSG:28992"):
        dtm_ahn.fetch_ahn_wcs((0, 0, 1, 1), tmp_path, "EPSG:4326")


def test_netherlands_fetch_forwards_tiles_dir_and_crs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, tiles_dir: object, crs: object) -> list[Path]:
        seen.append((bbox, tiles_dir, crs))
        return []

    monkeypatch.setattr(dtm_ahn, "fetch_ahn_wcs", fake)
    dtm_ahn.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None, "EPSG:28992")

    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", "EPSG:28992")]
