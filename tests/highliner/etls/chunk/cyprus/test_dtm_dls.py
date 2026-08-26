"""Tests for the Cyprus DLS 2019 DTM client."""
from pathlib import Path

import numpy as np
import pytest
import rasterio
import requests
from affine import Affine

from highliner.etls.chunk.cyprus import dtm_dls
from highliner.etls.chunk.dtm_core import NODATA

_METADATA = b"""<?xml version="1.0"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd">
  <gmd:EX_GeographicBoundingBox>
    <gmd:GeoBndBox>
      <gmd:westBL>32.4</gmd:westBL>
      <gmd:southBL>34.7</gmd:southBL>
      <gmd:eastBL>32.5</gmd:eastBL>
      <gmd:northBL>34.8</gmd:northBL>
    </gmd:GeoBndBox>
  </gmd:EX_GeographicBoundingBox>
</gmd:MD_Metadata>
"""


class _Response:
    def __init__(self, content: bytes = b"", text: str = "") -> None:
        self.content = content
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_get_retries_then_returns_the_successful_response(
        monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[str] = []

    def flaky(url: str, timeout: int) -> _Response:
        attempts.append(url)
        if len(attempts) < 3:
            raise requests.ConnectionError("boom")
        return _Response(content=b"ok")

    monkeypatch.setattr(requests, "get", flaky)
    monkeypatch.setattr("highliner.etls.chunk.cyprus.dtm_dls.time.sleep",
                        lambda _seconds: None)

    assert dtm_dls._get("https://example.test/sheet").content == b"ok"
    assert len(attempts) == 3


def test_get_raises_after_the_last_attempt(
        monkeypatch: pytest.MonkeyPatch) -> None:
    def always_fails(url: str, timeout: int) -> _Response:
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "get", always_fails)
    monkeypatch.setattr("highliner.etls.chunk.cyprus.dtm_dls.time.sleep",
                        lambda _seconds: None)

    with pytest.raises(requests.ConnectionError):
        dtm_dls._get("https://example.test/sheet")


def test_parse_sheet_metadata_reads_the_geographic_bounding_box() -> None:
    sheet = dtm_dls._parse_sheet_metadata("dtm_01.tif.xml", _METADATA)

    # The cached name drops only the metadata suffix; the sheet is the GeoTIFF.
    assert sheet["name"] == "dtm_01.tif"
    assert sheet["bbox"] == [32.4, 34.7, 32.5, 34.8]


def test_load_index_builds_caches_and_then_reuses_the_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    listing = ('<a href="dtm_01.tif.xml">a</a>'
               '<a href="dtm_02.tif.xml">b</a>'
               '<a href="dtm_01.tif.xml">duplicate</a>')
    fetched: list[str] = []

    def fake_get(url: str) -> _Response:
        fetched.append(url)
        if url == dtm_dls.DIRECTORY_URL:
            return _Response(text=listing)
        return _Response(content=_METADATA)

    monkeypatch.setattr(dtm_dls, "_get", fake_get)

    sheets = dtm_dls._load_index(tmp_path)

    assert [sheet["name"] for sheet in sheets] == ["dtm_01.tif", "dtm_02.tif"]
    assert (tmp_path / "index.json").exists()

    # A second call is served from index.json, so nothing else is fetched.
    fetched.clear()
    assert dtm_dls._load_index(tmp_path) == sheets
    assert fetched == []


def test_load_index_rejects_an_empty_directory_listing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dtm_dls, "_get",
                        lambda _url: _Response(text="<html>no sheets</html>"))

    with pytest.raises(RuntimeError, match="no sheet metadata"):
        dtm_dls._load_index(tmp_path)


def test_bbox_lonlat_covers_every_projected_corner() -> None:
    # A UTM 36N box over western Cyprus, back in ETRS89 degrees.
    west, south, east, north = dtm_dls._bbox_lonlat(
        (431000.0, 3822000.0, 441000.0, 3832000.0))

    assert 32.0 < west < east < 33.0
    assert 34.0 < south < north < 35.0


def test_download_sheet_writes_once_and_reuses_the_cached_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_get(url: str) -> _Response:
        calls.append(url)
        return _Response(content=b"raster-bytes")

    monkeypatch.setattr(dtm_dls, "_get", fake_get)

    path = dtm_dls._download_sheet(tmp_path / "source", "dtm_01.tif")

    assert path.read_bytes() == b"raster-bytes"
    assert calls == [dtm_dls.DIRECTORY_URL + "dtm_01.tif"]
    assert not list((tmp_path / "source").glob("*.part"))

    calls.clear()
    assert dtm_dls._download_sheet(tmp_path / "source", "dtm_01.tif") == path
    assert calls == []


def _write_source_sheet(path: Path) -> None:
    """A 1 m ETRS89 sheet carrying the DLS float nodata sentinel."""
    data = np.full((20, 20), 100.0, dtype="float32")
    data[0, 0] = dtm_dls.SOURCE_NODATA
    profile = {"driver": "GTiff", "dtype": "float32", "count": 1,
               "width": 20, "height": 20, "crs": dtm_dls.SOURCE_CRS,
               "nodata": dtm_dls.SOURCE_NODATA,
               "transform": Affine(1e-5, 0.0, 32.25, 0.0, -1e-5, 34.55)}
    with rasterio.open(path, "w", **profile) as sheet:
        sheet.write(data, 1)


def test_reproject_rewrites_the_sheet_in_utm_36n_with_shared_nodata(
        tmp_path: Path) -> None:
    source = tmp_path / "dtm_01.tif"
    _write_source_sheet(source)

    out = dtm_dls._reproject(source, tmp_path / "out.tif")

    with rasterio.open(out) as reprojected:
        assert reprojected.crs.to_string() == dtm_dls.CRS
        assert reprojected.nodata == NODATA
        # 5 m pixels, so the ~22 m sheet collapses to a handful of them.
        assert reprojected.res == (5.0, 5.0)
        values = reprojected.read(1)
        # The source sentinel is normalized, never carried through as data.
        assert not np.isclose(values, dtm_dls.SOURCE_NODATA).any()
        assert 100.0 in set(values.flatten())


def test_fetch_rejects_a_crs_it_cannot_process(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EPSG:32636"):
        dtm_dls.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", tmp_path,
                      "EPSG:25831")


def test_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cache_dir"):
        dtm_dls.fetch((431000.0, 3822000.0, 441000.0, 3832000.0),
                      tmp_path / "tiles", None, dtm_dls.CRS)


def test_fetch_reprojects_only_the_sheets_meeting_the_bbox(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = tmp_path / "cache"
    index = [{"name": "wanted.tif", "bbox": [32.2, 34.5, 32.3, 34.6]},
             {"name": "elsewhere.tif", "bbox": [33.5, 35.0, 33.6, 35.1]}]
    monkeypatch.setattr(dtm_dls, "_load_index", lambda _root: index)

    def fake_download(root: Path, name: str) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        _write_source_sheet(root / name)
        return root / name

    monkeypatch.setattr(dtm_dls, "_download_sheet", fake_download)

    tiles = dtm_dls.fetch((431000.0, 3822000.0, 432000.0, 3823000.0),
                          tmp_path / "tiles", cache, dtm_dls.CRS)

    assert [tile.name for tile in tiles] == ["wanted.tif"]
    with rasterio.open(tiles[0]) as tile:
        assert tile.crs.to_string() == dtm_dls.CRS
