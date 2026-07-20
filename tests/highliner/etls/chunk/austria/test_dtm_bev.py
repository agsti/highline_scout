from pathlib import Path

import numpy as np
import pytest
import rasterio
import requests
from rasterio.transform import from_origin
from shapely.geometry import box

from highliner.etls.chunk.austria import dtm_bev as dtm_austria


def _response(content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = content
    return response


def test_latest_bev_catalog_keeps_newest_publication_per_footprint() -> None:
    older: dtm_austria.Tile = {
        "url": "https://example.test/2024/tile.tif",
        "bbox_lonlat": [13.0, 47.0, 14.0, 48.0],
    }
    newer: dtm_austria.Tile = {
        "url": "https://example.test/2025/tile.tif",
        "bbox_lonlat": [13.0, 47.0, 14.0, 48.0],
    }
    other: dtm_austria.Tile = {
        "url": "https://example.test/2024/other.tif",
        "bbox_lonlat": [14.0, 47.0, 15.0, 48.0],
    }

    assert dtm_austria._latest_tiles([newer, older, other]) == [newer, other]


def test_bev_native_tile_names_filter_edge_touches_and_keep_unknown_names() -> None:
    query = box(4_650_000, 2_550_000, 4_660_000, 2_560_000)
    base = "https://example.test/ALS_DTM_"

    assert dtm_austria._native_tile_intersects(
        f"{base}CRS3035RES50000mN2550000E4650000.tif", query)
    assert not dtm_austria._native_tile_intersects(
        f"{base}CRS3035RES50000mN2550000E4600000.tif", query)
    assert dtm_austria._native_tile_intersects(
        "https://example.test/unrecognised-name.tif", query)


def test_bev_subset_is_materialized_at_five_metres_and_reused(
        tmp_path: Path) -> None:
    source = tmp_path / "source.tif"
    data = np.arange(400, dtype="float32").reshape(20, 20)
    with rasterio.open(
        source,
        "w",
        driver="GTiff",
        width=20,
        height=20,
        count=1,
        dtype="float32",
        crs="EPSG:3035",
        transform=from_origin(0, 20, 1, 1),
    ) as raster:
        raster.write(data, 1)

    first = dtm_austria._ensure_subset(
        str(source), (0.0, 10.0, 10.0, 20.0), tmp_path / "cache")
    first_stat = first.stat()
    second = dtm_austria._ensure_subset(
        str(source), (0.0, 10.0, 10.0, 20.0), tmp_path / "cache")

    assert second == first
    assert second.stat().st_mtime_ns == first_stat.st_mtime_ns
    with rasterio.open(first) as subset:
        assert (subset.width, subset.height) == (2, 2)
        assert subset.res == (5.0, 5.0)
        assert subset.crs.to_string() == "EPSG:3035"
        assert np.isfinite(subset.read(1)).all()


def test_bev_catalog_parses_only_intersecting_dtm_geotiffs(
        monkeypatch: pytest.MonkeyPatch) -> None:
    feed_url = "https://example.test/intersecting.xml"
    service = f'''<feed xmlns="http://www.w3.org/2005/Atom"
        xmlns:georss="http://www.georss.org/georss">
      <entry><georss:polygon>47 13 47 14 48 14 48 13</georss:polygon>
        <link rel="alternate" href="{feed_url}" /></entry>
      <entry><georss:polygon>40 1 40 2 41 2 41 1</georss:polygon>
        <link rel="alternate" href="https://example.test/far.xml" /></entry>
      <entry><georss:polygon>47 14 47 15 48 15 48 14</georss:polygon></entry>
      <entry><link rel="alternate" href="https://example.test/no-polygon.xml" />
      </entry>
    </feed>'''.encode()
    dataset = b'''<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><link rel="alternate"
        href="https://example.test/2024/DTM/tile.tif" /></entry>
      <entry><link rel="alternate"
        href="https://example.test/2025/DTM/tile.tif" /></entry>
      <entry><link rel="alternate"
        href="https://example.test/2025/DSM/tile.tif" /></entry>
      <entry><link rel="alternate"
        href="https://example.test/2025/DTM/readme.txt" /></entry>
    </feed>'''
    responses = {
        dtm_austria.ATOM_SERVICE_URL: _response(service),
        feed_url: _response(dataset),
    }
    monkeypatch.setattr(requests, "get", lambda url, timeout: responses[url])

    assert dtm_austria._download_catalog(box(12.5, 46.5, 14.5, 48.5)) == [{
        "url": "https://example.test/2025/DTM/tile.tif",
        "bbox_lonlat": [13.0, 47.0, 14.0, 48.0],
    }]


def test_fetch_bev_tiles_downloads_only_intersecting_catalog_tiles(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_download(url: str, _bbox: object, dest: Path) -> None:
        dest.write_bytes(url.encode())

    monkeypatch.setattr(dtm_austria, "_catalog", lambda _root, _query: [
        {"url": "https://example.test/a", "bbox_lonlat": [13, 47, 14, 48]},
        {"url": "https://example.test/b", "bbox_lonlat": [10, 46, 11, 47]},
    ])
    monkeypatch.setattr(dtm_austria, "_materialize_subset", fake_download)

    paths = dtm_austria.fetch_bev_tiles((13.2, 47.2, 13.8, 47.8), "EPSG:4326",
                                         tmp_path)

    assert len(paths) == 1
    assert paths[0].name.startswith("a_")
    assert paths[0].suffix == ".tif"


def test_fetch_bev_tiles_rejects_false_wgs84_bbox_overlap(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    selected: list[str] = []

    def fake_download(url: str, _bbox: object, dest: Path) -> None:
        selected.append(url)
        dest.write_bytes(url.encode())

    base = "https://data.bev.gv.at/download/ALS/DTM/20250915/"
    monkeypatch.setattr(dtm_austria, "_catalog", lambda _root, _query: [
        {"url": f"{base}ALS_DTM_CRS3035RES50000mN2550000E4600000.tif",
         "bbox_lonlat": [12, 45, 16, 48]},
        {"url": f"{base}ALS_DTM_CRS3035RES50000mN2550000E4650000.tif",
         "bbox_lonlat": [12, 45, 16, 48]},
    ])
    monkeypatch.setattr(dtm_austria, "_materialize_subset", fake_download)

    paths = dtm_austria.fetch_bev_tiles(
        (4636950, 2577950, 4649050, 2590050), "EPSG:3035", tmp_path)

    assert len(paths) == 1
    assert "E4600000" in paths[0].name
    assert len(selected) == 1
