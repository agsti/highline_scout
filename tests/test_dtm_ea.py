"""Tests for the Environment Agency LIDAR composite DTM client."""
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from highliner.etls.chunk import dtm_ea

EA_NODATA = -3.4028234663852886e+38   # float32 min, as shipped in EA tiles


def _write_1m_tif(path: Path, data: np.ndarray, origin: tuple[float, float]
                  ) -> None:
    with rasterio.open(
            path, "w", driver="GTiff", width=data.shape[1],
            height=data.shape[0], count=1, dtype="float32",
            crs="EPSG:27700", nodata=EA_NODATA,
            transform=from_origin(origin[0], origin[1], 1.0, 1.0)) as dst:
        dst.write(data.astype("float32"), 1)


def test_tile_ids_single_tile() -> None:
    # ST4550 spans 345000-350000 easting, 150000-155000 northing (verified
    # against a real downloaded tile's GeoTIFF bounds).
    assert dtm_ea.tile_ids((345000, 150000, 350000, 155000)) == ["ST4550"]


def test_tile_ids_span_multiple_tiles() -> None:
    ids = dtm_ea.tile_ids((344000, 149000, 351000, 156000))
    assert ids == ["ST4045", "ST4050", "ST4055",
                   "ST4545", "ST4550", "ST4555",
                   "ST5045", "ST5050", "ST5055"]


def test_tile_ids_cross_100km_square() -> None:
    # SW/SV boundary at easting 100000 west of Land's End.
    ids = dtm_ea.tile_ids((95000, 20000, 105000, 25000))
    assert ids == ["SV9520", "SW0020"]


def test_resample_to_5m_averages_valid_cells(tmp_path: Path) -> None:
    # A 10x10 1 m tile becomes 2x2 at 5 m; each output cell averages its
    # 5x5 input block.
    data = np.zeros((10, 10))
    data[:5, :5] = 100.0    # NW block
    data[:5, 5:] = 200.0    # NE block
    data[5:, :5] = 10.0     # SW block
    data[5:, 5:] = 20.0     # SE block
    src = tmp_path / "in.tif"
    _write_1m_tif(src, data, (345000.0, 155000.0))

    dest = tmp_path / "out.tif"
    dtm_ea.resample_to_5m(src, dest)

    with rasterio.open(dest) as out:
        assert out.res == (5.0, 5.0)
        assert out.crs.to_epsg() == 27700
        assert out.nodata == dtm_ea.NODATA
        grid = out.read(1)
    assert grid.shape == (2, 2)
    np.testing.assert_allclose(grid, [[100.0, 200.0], [10.0, 20.0]])


def test_resample_to_5m_ignores_nodata_and_keeps_empty_blocks_nodata(
        tmp_path: Path) -> None:
    data = np.full((10, 10), EA_NODATA)
    data[:5, :5] = 100.0
    data[0, 5] = 40.0       # single valid cell in an otherwise-nodata block
    src = tmp_path / "in.tif"
    _write_1m_tif(src, data, (345000.0, 155000.0))

    dest = tmp_path / "out.tif"
    dtm_ea.resample_to_5m(src, dest)

    with rasterio.open(dest) as out:
        grid = out.read(1)
    assert grid[0, 0] == 100.0          # full valid block: plain average
    assert grid[0, 1] == 40.0           # sea sentinel excluded from average
    assert grid[1, 0] == dtm_ea.NODATA  # all-nodata block stays nodata
    assert grid[1, 1] == dtm_ea.NODATA


def _fake_download(tmp_path: Path, calls: list[str]
                   ) -> "Callable[[str, Path], bool]":
    """Downloader stub writing a zip with a tiny 1 m tile named per EA."""
    import zipfile

    def download(tile_id: str, dest: Path) -> bool:
        calls.append(tile_id)
        tif = tmp_path / f"{tile_id}_DTM_1m.tif"
        x_km = int(tile_id[2:4])
        y_km = int(tile_id[4:6])
        origin = (300000.0 + x_km * 1000, 100000.0 + y_km * 1000 + 10)
        _write_1m_tif(tif, np.full((10, 10), 7.0), origin)
        with zipfile.ZipFile(dest, "w") as z:
            z.write(tif, tif.name)
        return True

    return download


def _stub_catalog(monkeypatch: pytest.MonkeyPatch, tiles: set[str]) -> None:
    monkeypatch.setattr(dtm_ea, "catalog", lambda root: frozenset(tiles))


def test_fetch_downloads_resamples_and_cleans_up(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(dtm_ea, "_download_zip", _fake_download(tmp_path, calls))
    _stub_catalog(monkeypatch, {"ST4550"})

    paths = dtm_ea.fetch_ea_lidar((345000, 150000, 350000, 155000), tmp_path)

    assert calls == ["ST4550"]
    assert [p.name for p in paths] == ["ST4550_5m.tif"]
    with rasterio.open(paths[0]) as out:
        assert out.res == (5.0, 5.0)
    root = tmp_path / "ea-lidar-5m"
    assert not list(root.glob("*.zip"))      # raw archive removed
    assert not list(root.glob("*_1m.tif"))   # raw 1 m raster removed

    # Second fetch is served from cache without touching the network.
    again = dtm_ea.fetch_ea_lidar((345000, 150000, 350000, 155000), tmp_path)
    assert again == paths
    assert calls == ["ST4550"]


def test_ensure_tile_skips_tiles_outside_the_catalog(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The tile endpoint 500s (a generic error, indistinguishable from an
    # outage) for any gridref outside its catalog — sea, Scotland, the ~1%
    # lidar gaps. The cached catalog is the authority: uncataloged tiles are
    # never requested at all.
    calls: list[str] = []
    monkeypatch.setattr(dtm_ea, "_download_zip", _fake_download(tmp_path, calls))
    _stub_catalog(monkeypatch, {"ST4550"})

    assert dtm_ea.ensure_tile("SV0000", tmp_path) is None
    assert calls == []
    assert dtm_ea.fetch_ea_lidar((340000, 150000, 350000, 155000),
                                 tmp_path) != []
    assert calls == ["ST4550"]     # ST4045/ST4050 skipped without a request


def test_ensure_tile_returns_path_and_caches(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(dtm_ea, "_download_zip", _fake_download(tmp_path, calls))
    _stub_catalog(monkeypatch, {"ST4550"})

    path = dtm_ea.ensure_tile("ST4550", tmp_path)
    assert path is not None
    assert path.name == "ST4550_5m.tif"
    assert path.exists()
    # Cached: no second download.
    assert dtm_ea.ensure_tile("ST4550", tmp_path) == path
    assert calls == ["ST4550"]


def test_catalog_queries_every_block_once_then_reads_disk(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocks: list[tuple[float, float, float, float]] = []

    def fake_query(block: tuple[float, float, float, float]) -> set[str]:
        blocks.append(block)
        return {"ST4550"} if block[0] == 300000 and block[1] == 100000 else set()

    monkeypatch.setattr(dtm_ea, "_query_block", fake_query)

    root = tmp_path / "ea-lidar-5m"
    root.mkdir(parents=True)
    tiles = dtm_ea.catalog(root)
    assert tiles == frozenset({"ST4550"})
    assert len(blocks) == 49       # 7x7 100 km blocks over the coverage bbox
    assert (root / "catalog.json").exists()

    # Second call is served from disk.
    assert dtm_ea.catalog(root) == tiles
    assert len(blocks) == 49


def test_download_zip_retries_transient_errors_then_raises(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    import requests

    attempts: list[str] = []

    class FakeResponse:
        status_code = 500

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def raise_for_status(self) -> None:
            raise requests.HTTPError("500 Server Error")

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        attempts.append(url)
        return FakeResponse()

    # dtm_ea imports these modules, so patching the shared objects reaches it
    # without relying on implicit re-exports mypy rejects.
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    with pytest.raises(requests.HTTPError):
        dtm_ea._download_zip("ST4550", tmp_path / "t.zip")
    assert len(attempts) == 4


def test_fetch_tiles_dispatches_ea_lidar(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk import dtm

    seen: list[tuple[object, Path]] = []

    def fake_fetch(bbox: object, cache: Path) -> list[Path]:
        seen.append((bbox, cache))
        return []

    monkeypatch.setattr(dtm_ea, "fetch_ea_lidar", fake_fetch)

    dtm.fetch_tiles((345000, 150000, 350000, 155000), tmp_path / "tiles",
                    source="ea_lidar_1m", crs="EPSG:27700",
                    cache_dir=tmp_path / "cache")
    assert seen == [((345000, 150000, 350000, 155000), tmp_path / "cache")]

    with pytest.raises(ValueError, match="cache_dir"):
        dtm.fetch_tiles((0, 0, 1, 1), tmp_path / "tiles",
                        source="ea_lidar_1m", crs="EPSG:27700")
