from pathlib import Path

import numpy as np
import pytest
import rasterio
import requests
from affine import Affine

from highliner.etls.chunk.dtm_core import SEA_SENTINEL
from highliner.etls.chunk.united_states import dtm_3dep


def _geotiff_bytes(data: np.ndarray) -> bytes:
    """Serialise ``data`` as a minimal EPSG:5070 GeoTIFF, as the server would."""
    transform = Affine(5.0, 0.0, 100_000.0, 0.0, -5.0, 200_000.0)
    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", height=data.shape[0],
                          width=data.shape[1], count=1, dtype="float32",
                          crs="EPSG:5070", transform=transform) as dst:
            dst.write(data.astype("float32"), 1)
        raw: bytes = memfile.read()
        return raw


def _response(status: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def test_pixel_dims_render_the_bbox_at_5m() -> None:
    assert dtm_3dep._pixel_dims((0, 0, 12_100, 12_100), 5.0) == (2420, 2420)
    # Never collapses to a zero-length request.
    assert dtm_3dep._pixel_dims((0, 0, 1, 1), 5.0) == (1, 1)


def test_fetch_3dep_masks_ocean_and_builds_the_export_request(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    # Land elevations plus an exact-0.0 ocean corner and a real sea-level lake.
    grid = np.array([[1200.0, 0.0], [850.5, 0.0]], dtype="float32")

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return _response(200, _geotiff_bytes(grid))

    monkeypatch.setattr(requests, "get", fake_get)

    paths = dtm_3dep.fetch_3dep((300_000, 400_000, 310_000, 412_000),
                                tmp_path, "EPSG:5070")

    assert paths == [tmp_path / "t_300000_400000.tif"]
    params = calls[0]
    assert params["bboxSR"] == 5070 and params["imageSR"] == 5070
    assert params["bbox"] == "300000,400000,310000,412000"
    assert params["size"] == "2000,2400"        # 10000/5 x 12000/5
    assert params["format"] == "tiff"

    with rasterio.open(paths[0]) as src:
        out = src.read(1)
        assert src.nodata == SEA_SENTINEL
    # Ocean 0.0 became the sea sentinel; genuine elevations are untouched.
    assert (out == SEA_SENTINEL).sum() == 2
    assert out[0, 0] == 1200.0 and out[1, 0] == 850.5


def test_fetch_3dep_rejects_a_non_raster_body(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get", lambda *a, **k: _response(
        200, b'{"error":{"code":400,"message":"Unable to complete"}}'))
    with pytest.raises(RuntimeError, match="did not return a GeoTIFF"):
        dtm_3dep.fetch_3dep((0, 0, 10_000, 10_000), tmp_path, "EPSG:5070")


def test_fetch_3dep_guards_the_export_pixel_cap(tmp_path: Path) -> None:
    huge = (0, 0, 5.0 * dtm_3dep.MAX_EXPORT_PX + 5_000, 10_000)
    with pytest.raises(RuntimeError, match="exceeds"):
        dtm_3dep.fetch_3dep(huge, tmp_path, "EPSG:5070")


def test_fetch_wraps_the_call_in_the_transient_retry(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    attempts = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.Timeout("temporary timeout")
        return _response(200, _geotiff_bytes(np.array([[10.0]], dtype="float32")))

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda _: None)

    paths = dtm_3dep.fetch((0, 0, 5, 5), tmp_path, None, "EPSG:5070")
    assert len(paths) == 1 and attempts == 2


def test_fetch_ignores_cache_dir_and_extracts_the_epsg(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        seen.append(params)
        return _response(200, _geotiff_bytes(np.array([[3.0]], "float32")))

    monkeypatch.setattr(requests, "get", fake_get)
    dtm_3dep.fetch((0, 0, 5, 5), tmp_path, Path("/unused/cache"), "EPSG:3338")
    assert seen[0]["bboxSR"] == 3338
