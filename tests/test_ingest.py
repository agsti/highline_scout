from pathlib import Path
import numpy as np
import pytest
from highliner.repositories import dtm as ingest


def _fake_asc(bbox: tuple[float, float, float, float], width: int, height: int, dest: Path) -> Path:
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


def test_estimate_tiles_matches_grid() -> None:
    # 2000 x 1500 m at 5 m, 175 px tiles (875 m) -> 3 x 2 = 6
    n = ingest.estimate_tiles((484000, 4646000, 486000, 4647500),
                              res=5.0, tile_px=175)
    assert n == 6


def test_tile_specs_covers_grid() -> None:
    specs = list(ingest.tile_specs((484000, 4646000, 486000, 4647500),
                                   res=5.0, tile_px=175))
    assert len(specs) == 6
    for tb, w, h in specs:
        assert w > 0 and h > 0


def test_fetch_tiles_skips_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path) -> Path:
        if int(bbox[0]) == 484000:           # simulate out-of-coverage column
            raise RuntimeError("ICGC WCS did not return ArcGrid data")
        return _fake_asc(bbox, width, height, dest)
    monkeypatch.setattr(ingest, "_download_tile", fake_download)

    paths = ingest.fetch_tiles((484000, 4646000, 486000, 4647500),
                               tmp_path / "tiles", res=5.0, tile_px=175)
    assert len(paths) == 4                    # 2 of 6 specs failed
    assert all(p.exists() for p in paths)


def test_fetch_tiles_idee_uses_tif_tiles_and_region_crs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_download(
        bbox: tuple[float, float, float, float],
        width: int,
        height: int,
        dest: Path,
        crs: str,
    ) -> Path:
        calls.append((bbox, width, height, dest.suffix, crs))
        dest.write_bytes(b"II fake tif")
        return dest

    monkeypatch.setattr(ingest, "_download_idee_tile", fake_download)

    paths = ingest.fetch_tiles((188000, 3060000, 188500, 3060500),
                               tmp_path / "tiles", source="idee",
                               crs="EPSG:4083")
    assert paths
    assert all(p.suffix == ".tif" for p in paths)
    assert {c[4] for c in calls} == {"EPSG:4083"}


def test_raster_from_tiles_merges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest, "_download_tile", _fake_asc)
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
