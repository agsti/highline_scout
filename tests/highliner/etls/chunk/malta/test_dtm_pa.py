from pathlib import Path

import pytest
import requests

from highliner.etls.chunk.malta import dtm_pa


def _response(status: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def test_fetch_pa_wcs_requests_the_4_8m_pyramid_and_writes_geotiff(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    requested: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        requested.append(params)
        return _response(200, b"TIFF")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(dtm_pa, "_rewrite_nodata", lambda path: None)

    paths = dtm_pa.fetch_pa_wcs(
        (450_000, 3_970_000, 450_100, 3_970_100), tmp_path, "EPSG:32633")

    assert paths == [tmp_path / "t_450000_3970000.tif"]
    assert paths[0].read_bytes() == b"TIFF"
    assert requested[0]["coverageId"] == "dtm_1m_2018_32"
    assert requested[0]["subset"] == ["E(450000,450100)",
                                      "N(3970000,3970100)"]


def test_fetch_pa_wcs_rejects_a_non_national_crs(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="EPSG:32633"):
        dtm_pa.fetch_pa_wcs((0, 0, 1, 1), tmp_path, "EPSG:4326")
