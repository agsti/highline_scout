from pathlib import Path
import pytest
import rasterio
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


def test_fetch_tiles_builds_mosaic_and_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_download(bbox: tuple[float, float, float, float], width: int, height: int, dest: Path) -> Path:
        calls.append(bbox)
        return _fake_asc(bbox, width, height, dest)
    monkeypatch.setattr(ingest, "_download_tile", fake_download)

    # 2000 x 1500 m at 5 m, tile cap 175 px (875 m) -> 3 x 2 = 6 tiles
    bbox = (484000, 4646000, 486000, 4647500)
    p = ingest.fetch_dtm(bbox, region="t", data_dir=tmp_path,
                         res=5.0, tile_px=175)
    assert p.name == "mosaic.tif" and p.exists()
    assert len(calls) == 6

    with rasterio.open(p) as ds:
        assert ds.crs.to_string() == "EPSG:25831"
        assert abs(ds.res[0] - 5.0) < 1e-6
        assert (ds.read(1) == 100.0).any()

    # second call hits the mosaic cache: no further downloads
    ingest.fetch_dtm(bbox, region="t", data_dir=tmp_path, res=5.0, tile_px=175)
    assert len(calls) == 6


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
    def fake_download(bbox, width, height, dest):
        if int(bbox[0]) == 484000:           # simulate out-of-coverage column
            raise RuntimeError("ICGC WCS did not return ArcGrid data")
        return _fake_asc(bbox, width, height, dest)
    monkeypatch.setattr(ingest, "_download_tile", fake_download)

    paths = ingest.fetch_tiles((484000, 4646000, 486000, 4647500),
                               tmp_path / "tiles", res=5.0, tile_px=175)
    assert len(paths) == 4                    # 2 of 6 specs failed
    assert all(p.exists() for p in paths)


def test_raster_from_tiles_merges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest, "_download_tile", _fake_asc)
    paths = ingest.fetch_tiles((484000, 4646000, 486000, 4647500),
                               tmp_path / "tiles", res=5.0, tile_px=175)
    r = ingest.raster_from_tiles(paths, res=5.0)
    assert r is not None and r.res == 5.0
    assert (r.data == 100.0).any()


def test_raster_from_tiles_empty_is_none() -> None:
    assert ingest.raster_from_tiles([], res=5.0) is None


def test_progress_called_per_tile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download(bbox: tuple[float, float, float, float], width: int, height: int, dest: Path) -> Path:
        return _fake_asc(bbox, width, height, dest)
    monkeypatch.setattr(ingest, "_download_tile", fake_download)

    seen = []
    ingest.fetch_dtm((484000, 4646000, 486000, 4647500), region="p",
                     data_dir=tmp_path, res=5.0, tile_px=175,
                     progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (6, 6)            # finishes at total
    assert [d for d, _ in seen] == [1, 2, 3, 4, 5, 6]  # monotonic
    assert all(t == 6 for _, t in seen)  # total constant
