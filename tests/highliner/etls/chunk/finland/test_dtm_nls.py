from pathlib import Path

import pytest
import requests

from highliner.etls.chunk.finland import dtm_nls


def _response(status: int, content: bytes = b"") -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def test_nls_wcs_uses_basic_auth_and_5m_output(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_get(url: str, *, params: dict[str, object], auth: tuple[str, str],
                 timeout: int) -> requests.Response:
        seen.update(url=url, params=params, auth=auth, timeout=timeout)
        return _response(200, b"II*\x00terrain")

    monkeypatch.setattr(requests, "get", fake_get)

    dest = tmp_path / "tile.tif"
    out = dtm_nls.download_tile(
        (496_000, 7_181_000, 501_000, 7_186_000), 1_000, 1_000, dest,
        "test-key")

    assert out == dest
    assert dest.read_bytes() == b"II*\x00terrain"
    assert seen["auth"] == ("test-key", "")
    assert seen["params"] == {
        "service": "WCS", "version": "2.0.1", "request": "GetCoverage",
        "coverageId": "korkeusmalli_2m",
        "subset": ["E(496000,501000)", "N(7181000,7186000)"],
        "format": "image/tiff", "scaleFactor": "0.4",
        "geotiff:compression": "LZW",
    }


def test_nls_wcs_rejects_a_non_raster_response(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get",
                        lambda *_args, **_kwargs: _response(200, b"<Exception/>"))

    with pytest.raises(RuntimeError, match="did not return a GeoTIFF"):
        dtm_nls.download_tile((0, 0, 5_000, 5_000), 1_000, 1_000,
                              tmp_path / "tile.tif", "test-key")


def test_nls_fetch_requires_api_key_and_tiles_wcs_requests(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HIGHLINER_NLS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="HIGHLINER_NLS_API_KEY"):
        dtm_nls.fetch((0, 0, 1, 1), tmp_path, None, "EPSG:3067")

    monkeypatch.setenv("HIGHLINER_NLS_API_KEY", "test-key")
    seen: dict[str, object] = {}

    def fake_grid(bbox: object, tiles_dir: object, download: object, ext: object,
                  **kwargs: object) -> list[Path]:
        seen.update(bbox=bbox, tiles_dir=tiles_dir, download=download, ext=ext,
                    **kwargs)
        return [tmp_path / "t_0_0.tif"]

    monkeypatch.setattr(dtm_nls, "fetch_tile_grid", fake_grid)
    assert dtm_nls.fetch((0, 0, 12_000, 12_000), tmp_path, None,
                         "EPSG:3067") == [tmp_path / "t_0_0.tif"]
    assert (seen["bbox"], seen["tiles_dir"]) == ((0, 0, 12_000, 12_000), tmp_path)
    assert seen["res"] == 5.0
    assert seen["tile_px"] == 1_000


def test_nls_fetch_rejects_non_native_crs(tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIGHLINER_NLS_API_KEY", "test-key")
    with pytest.raises(ValueError, match="EPSG:3067"):
        dtm_nls.fetch((0, 0, 1, 1), tmp_path, None, "EPSG:4326")
