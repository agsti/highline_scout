"""Tests for the swissALTI3D terrain source."""

from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import rasterio
import requests
from rasterio.transform import from_origin

from highliner.etls.chunk import dtm_core


def _feature(tile: str, year: int, *, gsd: float = 2.0) -> dict[str, Any]:
    filename = f"swissalti3d_{year}_{tile}_{gsd:g}_2056_5728.tif"
    return {
        "id": f"swissalti3d_{year}_{tile}",
        "properties": {"datetime": f"{year}-01-01T00:00:00Z"},
        "assets": {
            filename: {
                "href": f"https://data.geo.admin.ch/{filename}",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "gsd": gsd,
                "proj:epsg": 2056,
            },
        },
    }


def test_latest_assets_selects_newest_two_metre_cog_per_tile() -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    features = [
        _feature("2633-1155", 2019),
        _feature("2633-1155", 2025),
        _feature("2634-1155", 2021, gsd=0.5),
        _feature("2634-1155", 2021),
    ]

    assets = dtm_swissalti._latest_assets(features)

    assert assets == [
        {
            "filename": "swissalti3d_2025_2633-1155_2_2056_5728.tif",
            "href": ("https://data.geo.admin.ch/"
                     "swissalti3d_2025_2633-1155_2_2056_5728.tif"),
        },
        {
            "filename": "swissalti3d_2021_2634-1155_2_2056_5728.tif",
            "href": ("https://data.geo.admin.ch/"
                     "swissalti3d_2021_2634-1155_2_2056_5728.tif"),
        },
    ]


def test_catalog_query_follows_next_page() -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    pages = {
        dtm_swissalti.ITEMS_URL: {
            "features": [_feature("2633-1155", 2019)],
            "links": [{"rel": "next", "href": "https://example.test/page-2"}],
        },
        "https://example.test/page-2": {
            "features": [_feature("2633-1155", 2025)],
            "links": [],
        },
    }

    class Response:
        def __init__(self, body: dict[str, Any]) -> None:
            self._body = body

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return self._body

    class Session:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str] | None]] = []

        def get(self, url: str, *, params: dict[str, str] | None = None,
                timeout: float) -> Response:
            self.calls.append((url, params))
            return Response(pages[url])

    session = Session()
    assets = dtm_swissalti._query_assets(
        cast(requests.Session, session),
        (2485000, 1075000, 2495000, 1085000), "EPSG:2056")

    assert assets[0]["filename"].startswith("swissalti3d_2025_")
    assert session.calls[0][0] == dtm_swissalti.ITEMS_URL
    assert session.calls[0][1] is not None
    assert session.calls[0][1]["limit"] == "100"
    assert session.calls[1] == ("https://example.test/page-2", None)


def test_swissalti_fetch_forwards_bbox_cache_and_crs(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    seen: dict[str, object] = {}

    def fake_fetch(bbox: dtm_core.Bbox, cache_dir: Path, crs: str) -> list[Path]:
        seen.update(bbox=bbox, cache_dir=cache_dir, crs=crs)
        return [cache_dir / "swissalti3d_5m" / "tile_5m.tif"]

    monkeypatch.setattr(dtm_swissalti, "fetch_swissalti_tiles", fake_fetch)
    bbox = (2633000.0, 1155000.0, 2634000.0, 1156000.0)

    paths = dtm_swissalti.fetch(
        bbox, tmp_path / "tiles", tmp_path / "cache", "EPSG:2056")

    assert paths == [tmp_path / "cache" / "swissalti3d_5m" / "tile_5m.tif"]
    assert seen == {
        "bbox": bbox,
        "cache_dir": tmp_path / "cache",
        "crs": "EPSG:2056",
    }


def test_download_rejects_non_tiff_and_discards_part(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def raise_for_status(self) -> None:
            pass

        def iter_content(self, _size: int) -> list[bytes]:
            return [b"<html>not a raster</html>"]

    monkeypatch.setattr(
        "highliner.etls.chunk.switzerland.dtm_swissalti.requests.get",
        lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        "highliner.etls.chunk.switzerland.dtm_swissalti.time.sleep",
        lambda _delay: None)
    dest = tmp_path / "tile.tif"

    with pytest.raises(RuntimeError, match="did not return valid 2 m GeoTIFF"):
        dtm_swissalti._download_tile("https://example.test/tile.tif", dest)

    assert not dest.exists()
    assert not list(tmp_path.glob("*.part"))


def _write_raster(path: Path, *, resolution: float = 2.0,
                  crs: str = "EPSG:2056", nodata: float = -9999.0) -> None:
    size = int(1000 / resolution)
    values = np.full((size, size), 1000.0, dtype="float32")
    values[:5, :5] = nodata
    with rasterio.open(
        path, "w", driver="GTiff", width=size, height=size, count=1,
        dtype="float32", crs=crs, nodata=nodata,
        transform=from_origin(2633000, 1156000, resolution, resolution),
    ) as dataset:
        dataset.write(values, 1)


def test_resample_to_5m_preserves_grid_and_nodata(tmp_path: Path) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    source = tmp_path / "source.tif"
    dest = tmp_path / "derived.tif"
    _write_raster(source)

    dtm_swissalti._resample_to_5m(source, dest)

    with rasterio.open(dest) as dataset:
        assert dataset.crs.to_epsg() == 2056
        assert dataset.res == (5.0, 5.0)
        assert (dataset.width, dataset.height) == (200, 200)
        assert dataset.nodata == -9999.0
        values = dataset.read(1)
        assert values[0, 0] == -9999.0
        assert values[-1, -1] == 1000.0


@pytest.mark.parametrize(
    ("resolution", "crs", "nodata"),
    [(5.0, "EPSG:2056", -9999.0),
     (2.0, "EPSG:25832", -9999.0),
     (2.0, "EPSG:2056", -999.0)],
)
def test_source_validation_rejects_wrong_metadata(
        tmp_path: Path, resolution: float, crs: str, nodata: float) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    path = tmp_path / "source.tif"
    _write_raster(path, resolution=resolution, crs=crs, nodata=nodata)

    assert not dtm_swissalti._valid_raster(
        path, resolution=2.0, nodata=-9999.0)


def test_source_validation_rejects_truncated_tiff(tmp_path: Path) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    path = tmp_path / "source.tif"
    path.write_bytes(b"II*\x00truncated")

    assert not dtm_swissalti._valid_raster(
        path, resolution=2.0, nodata=-9999.0)


def test_source_validation_rejects_wrong_tile_bounds(tmp_path: Path) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    path = tmp_path / "source.tif"
    _write_raster(path)

    assert not dtm_swissalti._valid_raster(
        path, resolution=2.0, nodata=-9999.0,
        bounds=(2634000, 1155000, 2635000, 1156000))


def test_invalid_download_is_retried_and_discarded(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    calls = 0

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def raise_for_status(self) -> None:
            pass

        def iter_content(self, _size: int) -> list[bytes]:
            nonlocal calls
            calls += 1
            return [b"II*\x00truncated"]

    monkeypatch.setattr(
        "highliner.etls.chunk.switzerland.dtm_swissalti.time.sleep",
        lambda _delay: None)
    monkeypatch.setattr(
        "highliner.etls.chunk.switzerland.dtm_swissalti.requests.get",
        lambda *args, **kwargs: Response())

    with pytest.raises(RuntimeError, match="valid 2 m GeoTIFF"):
        dtm_swissalti._download_tile(
            "https://example.test/tile.tif", tmp_path / "tile.tif")

    assert calls == dtm_swissalti._RETRY_ATTEMPTS
    assert not list(tmp_path.glob("*.part"))


def test_corrupted_derived_cache_is_rebuilt_at_5m(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    asset: dtm_swissalti.TileAsset = {
        "filename": "swissalti3d_2025_2633-1155_2_2056_5728.tif",
        "href": "https://example.test/source.tif",
    }
    cache_dir = tmp_path / "swissalti3d_5m"
    cache_dir.mkdir()
    dest = cache_dir / "swissalti3d_2025_2633-1155_2_2056_5728_5m.tif"
    dest.write_bytes(b"II*\x00truncated")
    downloads = 0

    def fake_download(_url: str, path: Path,
                      bounds: dtm_swissalti.Bbox | None = None) -> None:
        nonlocal downloads
        downloads += 1
        assert bounds == (2633000, 1155000, 2634000, 1156000)
        _write_raster(path)

    monkeypatch.setattr(dtm_swissalti, "_download_tile", fake_download)

    first = dtm_swissalti._ensure_tile(tmp_path, asset)
    second = dtm_swissalti._ensure_tile(tmp_path, asset)

    assert first == second == dest
    assert downloads == 1
    assert dtm_swissalti._valid_raster(
        dest, resolution=5.0, nodata=-9999.0,
        bounds=(2633000, 1155000, 2634000, 1156000))


def test_swissalti_fetch_delegates_to_cache_client(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, cache_root: object, crs: object) -> list[Path]:
        seen.append((bbox, cache_root, crs))
        return [tmp_path / "tile.tif"]

    monkeypatch.setattr(dtm_swissalti, "fetch_swissalti_tiles", fake)
    out = dtm_swissalti.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                              tmp_path / "cache", "EPSG:2056")

    assert out == [tmp_path / "tile.tif"]
    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "cache", "EPSG:2056")]


def test_swissalti_fetch_requires_cache_dir(tmp_path: Path) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti

    with pytest.raises(ValueError, match="swissalti3d source requires cache_dir"):
        dtm_swissalti.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                            "EPSG:2056")
