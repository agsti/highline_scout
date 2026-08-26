from pathlib import Path

import pytest
import requests

from highliner.etls.chunk.indonesia import dtm_demnas


def test_demnas_export_masks_zero_elevation_as_sea(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    content = _tiff_with_values(tmp_path, [0.0, 42.0])
    seen: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        seen.append(params)
        return _response(200, content)

    monkeypatch.setattr(requests, "get", fake_get)

    paths = dtm_demnas.fetch_demnas(
        (100_000, 9_000_000, 100_010, 9_000_005), tmp_path, "EPSG:32748")

    assert paths == [tmp_path / "t_100000_9000000.tif"]
    assert _read_values(paths[0]) == [-8888.0, 42.0]
    assert seen[0]["imageSR"] == 32748
    assert seen[0]["size"] == "2,1"


def test_demnas_rejects_non_tiff_success_body(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get",
                        lambda *args, **kwargs: _response(200, b'{"error": {}}'))

    with pytest.raises(RuntimeError, match="GeoTIFF"):
        dtm_demnas.fetch_demnas((1, 2, 3, 4), tmp_path, "EPSG:32748")


def test_demnas_fetch_forwards_to_retryable_export(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    expected = [tmp_path / "tile.tif"]
    monkeypatch.setattr(dtm_demnas, "fetch_demnas",
                        lambda bbox, tiles_dir, crs: expected)

    assert dtm_demnas.fetch((1, 2, 3, 4), tmp_path, None, "EPSG:32748") == expected


def _response(status: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def _tiff_with_values(tmp_path: Path, values: list[float]) -> bytes:
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    path = tmp_path / "source.tif"
    with rasterio.open(path, "w", driver="GTiff", width=len(values), height=1,
                       count=1, dtype="float32", crs="EPSG:32748",
                       transform=from_origin(0, 5, 5, 5)) as dst:
        dst.write(np.array([[values]], dtype="float32"))
    return path.read_bytes()


def _read_values(path: Path) -> list[float]:
    import rasterio

    with rasterio.open(path) as src:
        return [float(value) for value in src.read(1).ravel()]
