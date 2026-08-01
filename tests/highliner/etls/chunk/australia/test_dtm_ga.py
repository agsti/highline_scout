from pathlib import Path

import pytest
import requests

from highliner.etls.chunk.australia import dtm_ga


def test_fetch_ga_wcs_requests_a_5m_geotiff(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    response = requests.Response()
    response.status_code = 200
    response._content = b"II*\x00tiff"
    calls: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    paths = dtm_ga.fetch_ga_wcs((1, 2, 11, 12), tmp_path, "EPSG:3577")

    assert paths == [tmp_path / "t_1_2.tif"]
    assert paths[0].read_bytes() == b"II*\x00tiff"
    assert calls[0]["resx"] == 5
    assert calls[0]["response_crs"] == "EPSG:3577"


def test_fetch_ga_wcs_rejects_non_australian_albers(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="EPSG:3577"):
        dtm_ga.fetch_ga_wcs((1, 2, 3, 4), tmp_path, "EPSG:4326")
