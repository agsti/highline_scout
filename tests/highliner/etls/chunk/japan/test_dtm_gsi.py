from pathlib import Path

import numpy as np
import pytest
import rasterio
import requests

from highliner.etls.chunk.dtm_core import NODATA
from highliner.etls.chunk.japan import dtm_gsi


class _Response:
    def __init__(self, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError()


def test_gsi_rgb_decoder_handles_signed_heights_and_nodata() -> None:
    rgb = np.array([[[0, 128]], [[1, 0]], [[244, 0]]], dtype="uint8")
    decoded = dtm_gsi._decode(rgb)
    assert decoded[0, 0] == 5.0
    assert decoded[0, 1] == NODATA


def test_gsi_tile_range_covers_tiles_on_both_sides_of_equator_and_meridian() -> None:
    columns, rows = dtm_gsi._tile_range((-1.0, -1.0, 1.0, 1.0), "EPSG:3857")

    assert list(columns) == [8191, 8192]
    assert list(rows) == [8191, 8192]


def test_gsi_missing_tile_writes_a_nodata_raster(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    response = _Response(404)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response)
    dest = tmp_path / "missing.tif"

    assert dtm_gsi._download(1, 2, dest, "EPSG:3857") == dest

    with rasterio.open(dest) as tile:
        assert tile.crs.to_epsg() == 3857
        assert tile.read(1)[0, 0] == NODATA


def test_gsi_present_tile_is_written_with_the_requested_crs(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    response = _Response(200, b"png")
    written: list[tuple[bytes, int, int, Path, str]] = []
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response)
    monkeypatch.setattr(dtm_gsi, "_write_tile",
                        lambda *args: written.append(args))
    dest = tmp_path / "present.tif"

    assert dtm_gsi._download(1, 2, dest, "EPSG:32654") == dest
    assert written == [(b"png", 1, 2, dest, "EPSG:32654")]


def test_gsi_fetches_every_tile_in_the_requested_grid(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dtm_gsi, "_tile_range",
                        lambda bbox, crs: (range(3, 5), range(7, 9)))

    def write_tile(x: int, y: int, dest: Path, crs: str) -> Path:
        dest.write_text(f"{x},{y},{crs}")
        return dest

    monkeypatch.setattr(dtm_gsi, "_download_retry", write_tile)
    paths = dtm_gsi.fetch((0.0, 0.0, 1.0, 1.0), tmp_path, None, "EPSG:32654")

    assert [path.name for path in paths] == [
        "gsi_14_3_7.tif", "gsi_14_3_8.tif", "gsi_14_4_7.tif", "gsi_14_4_8.tif"]
    assert [path.read_text() for path in paths] == [
        "3,7,EPSG:32654", "3,8,EPSG:32654", "4,7,EPSG:32654", "4,8,EPSG:32654"]
