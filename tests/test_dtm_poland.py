from pathlib import Path

import pytest
import requests
from highliner.etls.chunk import dtm, dtm_poland


def test_fetch_poland_wcs_writes_ascii_grid_from_multipart_response(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Response:
        content = (b"--wcs\r\nContent-Type: image/x-aaigrid\r\n\r\n"
                   b"ncols 1\nnrows 1\nxllcorner 1\nyllcorner 2\n"
                   b"cellsize 5\n3\nPROJCS[\"x\"]\r\n--wcs--\r\n")

        def raise_for_status(self) -> None:
            return None

    calls: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object], timeout: int) -> Response:
        calls.append(params)
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)

    paths = dtm_poland.fetch_poland_wcs((100, 200, 110, 210), tmp_path, "EPSG:2180")

    assert paths == [tmp_path / "t_100_200.asc"]
    assert paths[0].read_text().endswith("cellsize 5\n3\n")
    assert calls[0]["scaleaxes"] == "x(0.2),y(0.2)"


def test_fetch_poland_wcs_rejects_a_non_national_crs(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="EPSG:2180"):
        dtm_poland.fetch_poland_wcs((0, 0, 1, 1), tmp_path, "EPSG:4326")


def test_fetch_tiles_dispatches_polish_wcs(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    expected = [tmp_path / "tile.asc"]
    monkeypatch.setattr(dtm_poland, "fetch_poland_wcs",
                        lambda bbox, tiles_dir, crs: expected)

    assert dtm.fetch_tiles((1, 2, 3, 4), tmp_path, source="poland_wcs",
                           crs="EPSG:2180") == expected
