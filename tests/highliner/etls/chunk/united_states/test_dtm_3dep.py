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


def test_fetch_splits_a_chunk_into_a_two_by_two_tile_grid(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return _response(200, _geotiff_bytes(np.array([[7.0]], "float32")))

    monkeypatch.setattr(requests, "get", fake_get)

    # A real chunk halo bbox: 10000 m core + 2 x 1050 m halo = 12100 m = 2420 px.
    paths = dtm_3dep.fetch((300_000, 400_000, 312_100, 412_100),
                           tmp_path, None, "EPSG:5070")

    assert sorted(p.name for p in paths) == [
        "t_300000_400000.tif", "t_300000_406050.tif",
        "t_306050_400000.tif", "t_306050_406050.tif",
    ]
    # Every sub-request is a 1210 px square -- no slivers, none near the cap.
    assert {p["size"] for p in calls} == {"1210,1210"}
    assert len(calls) == 4


def test_download_tile_masks_ocean_and_builds_the_export_request(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    # Land elevations plus an exact-0.0 ocean corner and a real sea-level lake.
    grid = np.array([[1200.0, 0.0], [850.5, 0.0]], dtype="float32")

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return _response(200, _geotiff_bytes(grid))

    monkeypatch.setattr(requests, "get", fake_get)
    dest = tmp_path / "t_300000_400000.tif"

    out_path = dtm_3dep._download_tile(
        (300_000, 400_000, 310_000, 412_000), 2000, 2400, dest, epsg=5070)

    assert out_path == dest
    params = calls[0]
    assert params["bboxSR"] == 5070 and params["imageSR"] == 5070
    assert params["bbox"] == "300000,400000,310000,412000"
    assert params["size"] == "2000,2400"
    assert params["format"] == "tiff"

    with rasterio.open(dest) as src:
        out = src.read(1)
        assert src.nodata == SEA_SENTINEL
    # Ocean 0.0 became the sea sentinel; genuine elevations are untouched.
    assert (out == SEA_SENTINEL).sum() == 2
    assert out[0, 0] == 1200.0 and out[1, 0] == 850.5


def test_a_non_raster_body_fails_the_chunk_instead_of_dropping_a_tile(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """fetch_tile_grid drops a tile that raises RuntimeError. The ImageServer
    fills out-of-coverage footprints rather than erroring, so a non-raster body
    is a real failure and must propagate -- otherwise the merged raster gets a
    silent hole and the chunk is written and marked done anyway."""
    monkeypatch.setattr(requests, "get", lambda *a, **k: _response(
        200, b'{"error":{"code":400,"message":"Unable to complete"}}'))

    with pytest.raises(dtm_3dep.ExportError, match="did not return a GeoTIFF"):
        dtm_3dep.fetch((0, 0, 12_100, 12_100), tmp_path, None, "EPSG:5070")

    assert not issubclass(dtm_3dep.ExportError, RuntimeError)


def test_fetch_retries_a_transient_failure_per_tile(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    attempts = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.Timeout("temporary timeout")
        return _response(200, _geotiff_bytes(np.array([[10.0]], "float32")))

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda _: None)

    # A 5 m bbox is a single 1x1 px tile, so the retry count is deterministic.
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
