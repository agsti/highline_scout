from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import rasterio
import requests
from affine import Affine

from highliner.etls.chunk.dtm_core import NODATA

_X0 = 1_000_000.0
_Y0 = 2_000_000.0


def _feature(identifier: str, href: str) -> dict[str, Any]:
    return {"id": identifier, "assets": {"dtm": {"href": href}}}


def test_hrdem_catalog_returns_only_dtm_assets_and_follows_pages() -> None:
    from highliner.etls.chunk.canada import dtm_hrdem

    pages = {
        dtm_hrdem.ITEMS_URL: {
            "features": [_feature("first", "https://example.test/first.tif")],
            "links": [{"rel": "next", "href": "https://example.test/second"}],
        },
        "https://example.test/second": {
            "features": [_feature("second", "https://example.test/second.tif"),
                         {"id": "dsm-only", "assets": {}}],
            "links": [],
        },
    }

    class Response:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return self.body

    class Session:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str] | None]] = []

        def get(self, url: str, *, params: dict[str, str] | None = None,
                timeout: float) -> Response:
            self.calls.append((url, params))
            return Response(pages[url])

    session = Session()
    assets = dtm_hrdem._query_assets(
        cast(requests.Session, session), (0.0, 0.0, 1.0, 1.0), "EPSG:3979")

    assert assets == [
        {"id": "first", "href": "https://example.test/first.tif"},
        {"id": "second", "href": "https://example.test/second.tif"},
    ]
    assert session.calls[0][1] is not None
    assert session.calls[0][1]["limit"] == "100"
    assert len(session.calls[0][1]["bbox"].split(",")) == 4


def _write_source(path: Path, *, size: int = 100, res: float = 1.0) -> Path:
    """A 1 m EPSG:3979 raster standing in for one HRDEM DTM COG."""
    values = np.arange(size * size, dtype="float32").reshape(size, size)
    with rasterio.open(path, "w", driver="GTiff", width=size, height=size,
                       count=1, dtype="float32", crs="EPSG:3979",
                       nodata=-9999.0,
                       transform=Affine(res, 0, _X0, 0, -res, _Y0)) as dst:
        dst.write(values, 1)
    return path


def test_materialize_subset_resamples_the_window_to_five_metres(
        tmp_path: Path) -> None:
    from highliner.etls.chunk.canada import dtm_hrdem

    source = _write_source(tmp_path / "cog.tif")
    dest = tmp_path / "subset.tif"

    dtm_hrdem._materialize_subset(
        {"id": "cog", "href": str(source)},
        (_X0 + 10, _Y0 - 60, _X0 + 60, _Y0 - 10), "EPSG:3979", dest)

    with rasterio.open(dest) as out:
        # 50 m of 1 m source pixels, averaged down to the 5 m analysis grid.
        assert (out.width, out.height) == (10, 10)
        assert out.res == (dtm_hrdem.RES, dtm_hrdem.RES)
        assert out.nodata == NODATA
        assert out.crs.to_string() == "EPSG:3979"


def test_materialize_subset_keeps_nothing_when_the_cog_misses_the_bbox(
        tmp_path: Path) -> None:
    # The STAC query matches on lon/lat envelopes, which are supersets of both
    # the chunk and the acquisition footprint, so an asset can come back whose
    # raster does not actually cover the chunk. That is absence of data.
    from highliner.etls.chunk.canada import dtm_hrdem

    source = _write_source(tmp_path / "cog.tif")
    dest = tmp_path / "subset.tif"

    dtm_hrdem._materialize_subset(
        {"id": "cog", "href": str(source)},
        (_X0 + 10_000, _Y0 - 10_060, _X0 + 10_060, _Y0 - 10_000),
        "EPSG:3979", dest)

    assert not dest.exists()


def test_fetch_hrdem_tiles_materializes_a_repeated_asset_only_once(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.canada import dtm_hrdem

    source = _write_source(tmp_path / "cog.tif")
    asset: dict[str, str] = {"id": "cog", "href": str(source)}
    monkeypatch.setattr(dtm_hrdem, "_query_assets",
                        lambda *_args: [asset, dict(asset)])
    materialized = 0
    real = dtm_hrdem._materialize_subset

    def counted(*args: Any) -> None:
        nonlocal materialized
        materialized += 1
        real(*args)

    monkeypatch.setattr(dtm_hrdem, "_materialize_subset", counted)
    bbox = (_X0 + 10, _Y0 - 60, _X0 + 60, _Y0 - 10)

    tiles = dtm_hrdem.fetch_hrdem_tiles(bbox, tmp_path / "tiles", "EPSG:3979")

    assert len(tiles) == 1
    assert tiles[0].exists()
    assert materialized == 1


def test_fetch_writes_subsets_into_the_chunk_tiles_dir(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Subsets are cut to the chunk's own bbox, so they can never be reused by
    # another chunk. They must land directly in tiles_dir, which is what
    # shared._cleanup_transient_tiles unlinks — anywhere else grows without
    # bound and fills the runner's disk.
    from highliner.etls.chunk.canada import dtm_hrdem
    from highliner.etls.chunk.shared import _cleanup_transient_tiles

    source = _write_source(tmp_path / "cog.tif")
    monkeypatch.setattr(dtm_hrdem, "_query_assets",
                        lambda *_args: [{"id": "cog", "href": str(source)}])
    tiles_dir = tmp_path / "tiles"
    tiles_dir.mkdir()

    tiles = dtm_hrdem.fetch((_X0 + 10, _Y0 - 60, _X0 + 60, _Y0 - 10),
                            tiles_dir, tmp_path / "cache", "EPSG:3979")

    assert [path.parent for path in tiles] == [tiles_dir]
    assert not (tmp_path / "cache").exists()

    _cleanup_transient_tiles(tiles, tiles_dir)
    assert not any(path.exists() for path in tiles)
