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


def test_fetch_pa_wcs_clamps_the_subset_to_the_coverage_envelope(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The region bbox plus halo overhangs the coverage; rasdaman 404s on an
    out-of-envelope subset instead of clipping, so trim it before asking."""
    requested: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        requested.append(params)
        return _response(200, b"TIFF")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(dtm_pa, "_rewrite_nodata", lambda path: None)

    paths = dtm_pa.fetch_pa_wcs(
        (443_950, 3_957_950, 456_050, 3_970_050), tmp_path, "EPSG:32633")

    assert paths == [tmp_path / "t_443950_3959779.tif"]
    assert requested[0]["subset"] == ["E(443950,456050)",
                                      "N(3959779,3970050)"]


def test_fetch_pa_wcs_skips_a_chunk_wholly_outside_the_coverage(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        raise AssertionError("should not request terrain outside the coverage")

    monkeypatch.setattr(requests, "get", fail_get)

    assert dtm_pa.fetch_pa_wcs(
        (400_000, 3_900_000, 410_000, 3_910_000), tmp_path, "EPSG:32633") == []
