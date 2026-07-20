from pathlib import Path

import pytest
import requests

from highliner.etls.chunk import dtm
from highliner.etls.chunk.poland import dtm_wcs


def _response(status: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def _valid_grid_response() -> requests.Response:
    return _response(
        200,
        b"--wcs\r\nContent-Type: image/x-aaigrid\r\n\r\n"
        b"ncols 1\nnrows 1\nxllcorner 1\nyllcorner 2\n"
        b"cellsize 5\n3\nPROJCS[\"x\"]\r\n--wcs--\r\n",
    )


def test_fetch_poland_wcs_writes_ascii_grid_from_multipart_response(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return _valid_grid_response()

    monkeypatch.setattr(requests, "get", fake_get)

    paths = dtm_wcs.fetch_poland_wcs((100, 200, 110, 210), tmp_path, "EPSG:2180")

    assert paths == [tmp_path / "t_100_200.asc"]
    assert paths[0].read_text().endswith("cellsize 5\n3\n")
    assert calls[0]["scaleaxes"] == "x(0.2),y(0.2)"


def test_fetch_poland_wcs_treats_extent_error_as_empty(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    content = (
        b'<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows/2.0">'
        b'<ows:Exception exceptionCode="ExtentError" locator="extent">'
        b"<ows:ExceptionText>Image extent does not intersect</ows:ExceptionText>"
        b"</ows:Exception></ows:ExceptionReport>"
    )
    monkeypatch.setattr(requests, "get",
                        lambda *args, **kwargs: _response(400, content))

    assert dtm_wcs.fetch_poland_wcs(
        (89_000, 160_000, 89_100, 160_100), tmp_path, "EPSG:2180") == []


def test_fetch_tiles_does_not_retry_unrelated_poland_bad_request(
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
        dtm.fetch_tiles((100, 200, 110, 210), tmp_path,
                        source="poland_wcs", crs="EPSG:2180")
    assert attempts == 1


def test_fetch_tiles_retries_transient_poland_wcs_failure(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    attempts = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.Timeout("temporary timeout")
        return _valid_grid_response()

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda _: None)

    paths = dtm.fetch_tiles((100, 200, 110, 210), tmp_path,
                            source="poland_wcs", crs="EPSG:2180")

    assert len(paths) == 1
    assert attempts == 2


def test_fetch_poland_wcs_rejects_a_non_national_crs(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="EPSG:2180"):
        dtm_wcs.fetch_poland_wcs((0, 0, 1, 1), tmp_path, "EPSG:4326")


def test_fetch_tiles_dispatches_polish_wcs(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    expected = [tmp_path / "tile.asc"]
    monkeypatch.setattr(dtm_wcs, "fetch_poland_wcs",
                        lambda bbox, tiles_dir, crs: expected)

    assert dtm.fetch_tiles((1, 2, 3, 4), tmp_path, source="poland_wcs",
                           crs="EPSG:2180") == expected


def test_poland_fetch_retries_transient_failure(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429 is retried; the retry wrapper lives in Poland's fetcher now."""
    import requests

    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep",
                        lambda s: None)
    resp = requests.Response()
    resp.status_code = 429
    calls: list[int] = []

    def flaky(bbox: object, tiles_dir: object, crs: object) -> list[Path]:
        calls.append(1)
        if len(calls) == 1:
            raise requests.HTTPError(response=resp)
        return [tmp_path / "t.asc"]

    monkeypatch.setattr(dtm_wcs, "fetch_poland_wcs", flaky)

    assert dtm_wcs.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                         "EPSG:2180") == [tmp_path / "t.asc"]
    assert len(calls) == 2


def test_poland_fetch_forwards_tiles_dir_and_crs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, tiles_dir: object, crs: object) -> list[Path]:
        seen.append((bbox, tiles_dir, crs))
        return []

    monkeypatch.setattr(dtm_wcs, "fetch_poland_wcs", fake)
    dtm_wcs.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None, "EPSG:2180")

    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", "EPSG:2180")]
