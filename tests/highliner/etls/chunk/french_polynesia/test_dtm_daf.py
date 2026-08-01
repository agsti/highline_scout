from pathlib import Path
from typing import cast

import numpy as np
import pytest
import rasterio
import requests
from affine import Affine

from highliner.etls.chunk.dtm_core import SEA_SENTINEL
from highliner.etls.chunk.french_polynesia import dtm_daf


def _source_tiff() -> bytes:
    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(driver="GTiff", height=10, width=10, count=1,
                          dtype="float32", crs="EPSG:3297", nodata=-1,
                          transform=Affine(1, 0, 188000, 0, -1, 8067000)) as dst:
            dst.write(np.array(
                [[12.0] * 5 + [-1.0] * 5] * 5
                + [[42.0] * 5 + [-1.0] * 5] * 5, "float32"), 1)
        return cast(bytes, memfile.read())


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, _size: int) -> list[bytes]:
        return [self.content]


def test_fetch_caches_and_masks_the_daf_nodata(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get",
                        lambda *args, **kwargs: _Response(_source_tiff()))

    paths = dtm_daf.fetch((187000, 8049000, 210000, 8068000), tmp_path,
                          tmp_path / "cache", "EPSG:3297")

    assert paths == [tmp_path / "cache" / "moorea.tif"]
    with rasterio.open(paths[0]) as source:
        assert source.nodata == SEA_SENTINEL
        assert (source.read(1) == SEA_SENTINEL).sum() == 2


def test_fetch_rejects_an_uncovered_extent(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no DAF lidar"):
        dtm_daf.fetch((0, 0, 1, 1), tmp_path, tmp_path / "cache", "EPSG:4326")
