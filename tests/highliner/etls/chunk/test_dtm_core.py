import pytest
import requests

from highliner.etls.chunk import dtm_core


def _http_error(status: int, retry_after: str | None = None) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    if retry_after is not None:
        resp.headers["Retry-After"] = retry_after
    return requests.HTTPError(response=resp)


def test_tile_specs_covers_grid() -> None:
    specs = list(dtm_core.tile_specs((484000, 4646000, 486000, 4647500),
                                     res=5.0, tile_px=175))
    assert len(specs) == 6
    for _tb, w, h in specs:
        assert w > 0 and h > 0


def test_snap_expands_to_res_grid() -> None:
    assert dtm_core._snap((1.0, 2.0, 8.0, 9.0), 5.0) == (0.0, 0.0, 10.0, 10.0)


def test_epsg_code_strips_authority() -> None:
    assert dtm_core._epsg_code("EPSG:25831") == "25831"


def test_retry_delay_uses_exponential_backoff_without_response() -> None:
    assert dtm_core._retry_delay(0) == dtm_core.TILE_RETRY_BASE_S
    assert dtm_core._retry_delay(2) == dtm_core.TILE_RETRY_BASE_S * 4


def test_retry_delay_honors_larger_retry_after() -> None:
    resp = requests.Response()
    resp.headers["Retry-After"] = "30"
    assert dtm_core._retry_delay(0, resp) == 30.0


def test_retry_delay_ignores_http_date_retry_after() -> None:
    resp = requests.Response()
    resp.headers["Retry-After"] = "Wed, 21 Oct 2026 07:28:00 GMT"
    assert dtm_core._retry_delay(1, resp) == dtm_core.TILE_RETRY_BASE_S * 2


def test_download_with_retries_retries_transient_then_succeeds(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep",
                        lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def download() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _http_error(429, retry_after="7")
        return "ok"

    assert dtm_core._download_with_retries(download) == "ok"
    assert sleeps == [7.0, 7.0]


def test_download_with_retries_raises_when_attempts_exhausted(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda s: None)
    calls = {"n": 0}

    def download() -> str:
        calls["n"] += 1
        raise _http_error(503)

    with pytest.raises(requests.HTTPError):
        dtm_core._download_with_retries(download)
    assert calls["n"] == dtm_core.TILE_RETRY_ATTEMPTS


def test_download_with_retries_does_not_retry_non_transient(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda s: None)
    calls = {"n": 0}

    def download() -> str:
        calls["n"] += 1
        raise _http_error(404)

    with pytest.raises(requests.HTTPError):
        dtm_core._download_with_retries(download)
    assert calls["n"] == 1                        # 4xx (non-429) is not retried


def test_bbox_geom_lonlat_reprojects_to_wgs84() -> None:
    geom = dtm_core._bbox_geom_lonlat((484000, 4646000, 486000, 4647500),
                                      "EPSG:25831")
    minx, miny, maxx, maxy = geom.bounds
    assert 2.5 < minx < 3.0 and 2.5 < maxx < 3.0    # Catalonia, UTM 31N -> lon/lat
    assert 41.0 < miny < 42.5 and 41.0 < maxy < 42.5
    assert minx < maxx and miny < maxy
