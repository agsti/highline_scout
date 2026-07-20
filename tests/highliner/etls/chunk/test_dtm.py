from pathlib import Path

import numpy as np
import pytest

from highliner.etls.chunk import dtm as ingest
from highliner.etls.chunk.spain import dtm_icgc


def _fake_asc(bbox: tuple[float, float, float, float], width: int, height: int,
              dest: Path) -> Path:
    """Write a minimal valid ESRI ArcGrid tile of constant elevation 100."""
    minx, miny, maxx, maxy = bbox
    cell = (maxx - minx) / width
    header = [
        f"NCOLS {width}",
        f"NROWS {height}",
        f"XLLCORNER {minx}",
        f"YLLCORNER {miny}",
        f"CELLSIZE {cell}",
        "NODATA_VALUE -9999",
    ]
    body = "\n".join(" ".join("100.0" for _ in range(width))
                     for _ in range(height))
    dest.write_text("\n".join(header) + "\n" + body + "\n")
    return dest


def test_raster_from_tiles_merges(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dtm_icgc, "_download_tile", _fake_asc)
    paths = ingest.fetch_tiles((484000, 4646000, 486000, 4647500),
                               tmp_path / "tiles", res=5.0, tile_px=175)
    r = ingest.raster_from_tiles(paths, res=5.0)
    assert r is not None and r.res == 5.0
    assert (r.data == 100.0).any()


def test_raster_from_tiles_empty_is_none() -> None:
    assert ingest.raster_from_tiles([], res=5.0) is None


def test_raster_from_tiles_masks_sea_sentinel(tmp_path: Path) -> None:
    # A tile whose left half is sea (-8888). It must read back as NaN, not as
    # an 8888 m drop that makes every coastal cell a spurious cliff anchor.
    bbox = (484000, 4646000, 484500, 4646500)   # 100 x 100 px at 5 m
    w = h = 100
    header = [f"NCOLS {w}", f"NROWS {h}", f"XLLCORNER {bbox[0]}",
              f"YLLCORNER {bbox[1]}", "CELLSIZE 5.0", "NODATA_VALUE -9999"]
    row = " ".join((["-8888.0"] * (w // 2)) + (["100.0"] * (w - w // 2)))
    body = "\n".join(row for _ in range(h))
    asc = tmp_path / "t_484000_4646000.asc"
    asc.write_text("\n".join(header) + "\n" + body + "\n")

    r = ingest.raster_from_tiles([asc], res=5.0)
    assert r is not None
    assert np.isnan(r.data).any()               # sea half masked
    assert not (r.data == ingest.SEA_SENTINEL).any()
    assert (r.data == 100.0).any()              # land half kept
