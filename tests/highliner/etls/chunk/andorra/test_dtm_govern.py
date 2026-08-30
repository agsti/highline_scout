import io
import json
import runpy
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
import rasterio
import requests

from highliner.etls.chunk.andorra import dtm_govern


def _response(content: bytes, content_type: str = "application/zip",
              status: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.raw = io.BytesIO(content)
    response.headers["content-type"] = content_type
    return response


def _asc(text_target: Path, values: list[list[float]], *,
         xll: float = 528_500.0, yll: float = 20_000.0,
         cellsize: float = 0.5) -> Path:
    """Write a minimal ESRI ASCII grid, the shape the Andorra source ships."""
    header = (f"ncols {len(values[0])}\nnrows {len(values)}\n"
              f"xllcorner {xll}\nyllcorner {yll}\n"
              f"cellsize {cellsize}\nNODATA_value -9999\n")
    rows = "\n".join(" ".join(str(value) for value in row) for row in values)
    text_target.write_text(header + rows + "\n")
    return text_target


def _zip_with_grid(target: Path, values: list[list[float]]) -> Path:
    """Package one ASCII grid the way the download service does."""
    grid = _asc(target.with_suffix(".asc.tmp"), values)
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(f"{target.stem}.asc", grid.read_text())
    grid.unlink()
    return target


def test_government_client_selects_only_intersecting_dtm_tiles(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dtm_govern, "_query_tiles", lambda _bbox: [
        ("f5043", "mdt50cm2025asc/mdt50cm2025ascf5043.zip"),
        ("f5044", "mdt50cm2025asc/mdt50cm2025ascf5044.zip"),
    ])
    downloaded: list[str] = []

    def fake_download(path: str, target: Path) -> Path:
        downloaded.append(path)
        return _zip_with_grid(target, [[1.0] * 10] * 10)

    monkeypatch.setattr(dtm_govern, "_download", fake_download)

    paths = dtm_govern.fetch((540_000, 30_000, 550_000, 40_000), tmp_path,
                              tmp_path / "cache", "EPSG:27563")

    # Tiles reach the pipeline resampled to 5 m, not at the source's 0.5 m.
    assert [path.name for path in paths] == ["f5043_5m.tif", "f5044_5m.tif"]
    assert downloaded == [
        "mdt50cm2025asc/mdt50cm2025ascf5043.zip",
        "mdt50cm2025asc/mdt50cm2025ascf5044.zip",
    ]
    with rasterio.open(paths[0]) as raster:
        assert raster.res == (5.0, 5.0)
    # Only the 5 m result is kept; the 0.5 m archive and grid are transient.
    cache = tmp_path / "cache" / "govern_andorra_lidar_2025"
    assert sorted(p.name for p in cache.glob("*.zip")) == []
    assert sorted(p.name for p in tmp_path.glob("*.asc")) == []


def test_government_client_rejects_an_unexpected_crs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EPSG:27563"):
        dtm_govern.fetch((0, 0, 1, 1), tmp_path, tmp_path / "cache", "EPSG:4326")


def test_government_client_requires_a_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cache_dir"):
        dtm_govern.fetch((0, 0, 1, 1), tmp_path, None, "EPSG:27563")


def test_government_client_reuses_a_cached_five_metre_tile(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dtm_govern, "_query_tiles", lambda _bbox: [
        ("f5043", "mdt50cm2025asc/mdt50cm2025ascf5043.zip"),
    ])
    archives_dir = tmp_path / "cache" / "govern_andorra_lidar_2025"
    archives_dir.mkdir(parents=True)
    dtm_govern._resample(_asc(tmp_path / "f5043.asc", [[1.0] * 10] * 10),
                         archives_dir / "f5043_5m.tif")

    def fail_download(_path: str, _target: Path) -> Path:
        raise AssertionError("a cached tile must not be downloaded again")

    monkeypatch.setattr(dtm_govern, "_download", fail_download)

    paths = dtm_govern.fetch((0, 0, 1, 1), tmp_path / "tiles",
                             tmp_path / "cache", "EPSG:27563")

    assert [path.name for path in paths] == ["f5043_5m.tif"]


def test_resample_averages_the_half_metre_grid_onto_the_five_metre_grid(
        tmp_path: Path) -> None:
    # 20 x 20 cells at 0.5 m spans 10 m, so exactly 2 x 2 cells at 5 m. The
    # left half sits at 10 m, the right half at 20 m.
    values = [[10.0] * 10 + [20.0] * 10 for _ in range(20)]
    source = _asc(tmp_path / "f5043.asc", values)

    dest = dtm_govern._resample(source, tmp_path / "f5043_5m.tif")

    with rasterio.open(dest) as raster:
        assert raster.res == (5.0, 5.0)
        assert raster.crs.to_epsg() == 27563
        assert raster.nodata == -9999.0
        assert raster.bounds.left == 528_500.0
        assert raster.bounds.bottom == 20_000.0
        assert raster.read(1).tolist() == [[10.0, 20.0], [10.0, 20.0]]


def test_resample_keeps_nodata_out_of_the_average(tmp_path: Path) -> None:
    # One 5 m cell (5 x 5 at 1 m) mixing real ground with the source's -9999
    # must report the ground, not an average dragged toward the sentinel.
    values = [[-9999.0] * 5] + [[30.0] * 5 for _ in range(4)]
    source = _asc(tmp_path / "f5043.asc", values, cellsize=1.0)

    dest = dtm_govern._resample(source, tmp_path / "f5043_5m.tif")

    with rasterio.open(dest) as raster:
        assert raster.read(1).tolist() == [[30.0]]


def test_query_tiles_asks_the_wfs_for_the_bbox_in_the_source_crs(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    features = {"features": [
        {"properties": {"NOM": "f5043", "DES": "mdt50cm2025asc/f5043.zip"}},
    ]}

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append({"url": url, **params})
        return _response(json.dumps(features).encode(), "application/json")

    monkeypatch.setattr(requests, "get", fake_get)

    tiles = dtm_govern._query_tiles((540_000, 30_000, 550_000, 40_000))

    assert tiles == [("f5043", "mdt50cm2025asc/f5043.zip")]
    assert calls[0]["url"] == dtm_govern._WFS
    assert calls[0]["typeName"] == "mdt50cm2025asc"
    assert calls[0]["bbox"] == "540000,30000,550000,40000,EPSG:27563"


def test_download_streams_the_archive_under_an_obfuscated_path(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    requested: list[str] = []

    def fake_get(url: str, stream: bool, timeout: int) -> requests.Response:
        requested.append(url)
        return _response(b"PK\x03\x04payload")

    monkeypatch.setattr(requests, "get", fake_get)
    target = tmp_path / "f5043.zip"

    assert dtm_govern._download("mdt50cm2025asc/f5043.zip", target) == target
    assert target.read_bytes() == b"PK\x03\x04payload"
    assert not target.with_suffix(".part").exists()
    # The service takes an encrypted path, never the plain one.
    assert requested[0].startswith(dtm_govern._DOWNLOAD)
    assert "mdt50cm2025asc" not in requested[0]


def test_download_rejects_a_response_that_is_not_a_zip(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _response(
        b"<html>service unavailable</html>", "text/html"))

    with pytest.raises(RuntimeError, match="ZIP archive"):
        dtm_govern._download("mdt50cm2025asc/f5043.zip", tmp_path / "f5043.zip")


def test_extract_reuses_an_already_extracted_grid(tmp_path: Path) -> None:
    target = tmp_path / "f5043.asc"
    target.write_text("ncols 1\nnrows 1\n")

    assert dtm_govern._extract(tmp_path / "absent.zip", target) == target


def test_extract_rejects_an_archive_without_exactly_one_grid(
        tmp_path: Path) -> None:
    archive = tmp_path / "f5043.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("readme.txt", "no grid in here")

    with pytest.raises(RuntimeError, match="exactly one ASC grid"):
        dtm_govern._extract(archive, tmp_path / "f5043.asc")


def test_andorra_chunk_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.chunk.andorra.main.main") as entry:
        runpy.run_module("highliner.etls.chunk.andorra.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
