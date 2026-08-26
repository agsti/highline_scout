import json
import runpy
import subprocess
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
import rasterio
import requests
from rasterio.transform import from_origin

from highliner.etls.chunk.dtm_core import NODATA
from highliner.etls.chunk.ireland import dtm_gsi

_ITM_RING = [[500_000, 700_000], [510_000, 700_000],
             [510_000, 710_000], [500_000, 700_000]]


def _arcgis_feature(name: str = "P_602766",
                    url: str = "https://x/a.7z") -> dict[str, Any]:
    return {
        "attributes": {"DATA_NAME": name, "DATA_URL": url},
        "geometry": {"rings": [_ITM_RING]},
    }


def _page(features: list[dict[str, Any]],
          exceeded: bool = False) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(
        {"features": features, "exceededTransferLimit": exceeded}).encode()
    return response


def test_fetch_gsi_uses_intersecting_catalog_archives(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    catalog = {"features": [_arcgis_feature()]}
    monkeypatch.setattr(dtm_gsi, "_catalog", lambda: catalog)
    seen: list[tuple[str, Path]] = []

    def materialize(url: str, name: str, root: Path) -> Path:
        seen.append((url, root))
        path = root / f"{name}.tif"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"tif")
        return path

    monkeypatch.setattr(dtm_gsi, "_materialize", materialize)
    paths = dtm_gsi.fetch_gsi_lidar((504_000, 704_000, 506_000, 706_000),
                                     tmp_path, "EPSG:2157")

    assert paths == [tmp_path / "gsi-lidar-1m" / "P_602766.tif"]
    assert seen == [("https://x/a.7z", tmp_path / "gsi-lidar-1m")]


def test_fetch_gsi_skips_archives_outside_the_chunk(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dtm_gsi, "_catalog",
                        lambda: {"features": [_arcgis_feature()]})
    monkeypatch.setattr(dtm_gsi, "_materialize",
                        lambda *a: pytest.fail("must not download"))

    # A chunk far east of the survey ring; nothing intersects, nothing downloads.
    assert dtm_gsi.fetch_gsi_lidar((600_000, 700_000, 602_000, 702_000),
                                    tmp_path, "EPSG:2157") == []


def test_fetch_gsi_rejects_a_non_irish_tm_chunk(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only in EPSG:2157"):
        dtm_gsi.fetch_gsi_lidar((0, 0, 1, 1), tmp_path, "EPSG:25831")


def test_catalog_features_are_cached(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload: dict[str, list[object]] = {"features": []}
    monkeypatch.setattr(dtm_gsi, "_download_catalog", lambda: payload)

    assert dtm_gsi._load_catalog(tmp_path) == payload
    assert json.loads((tmp_path / "catalog.json").read_text()) == payload


def test_load_catalog_reuses_the_cached_file_without_downloading(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "catalog.json").write_text(json.dumps({"features": [1]}))
    monkeypatch.setattr(dtm_gsi, "_download_catalog",
                        lambda: pytest.fail("must not re-download"))

    assert dtm_gsi._load_catalog(tmp_path) == {"features": [1]}


def test_catalog_requires_a_configured_cache_root(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dtm_gsi, "_CATALOG_ROOT", None)
    with pytest.raises(RuntimeError, match="has not been configured"):
        dtm_gsi._catalog()


def test_download_catalog_follows_the_transfer_limit_across_pages(
        monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [_page([_arcgis_feature("A")], exceeded=True),
             _page([_arcgis_feature("B")], exceeded=False)]
    offsets: list[str] = []

    def fake_get(_url: str, params: dict[str, str],
                 timeout: int) -> requests.Response:
        offsets.append(params["resultOffset"])
        return pages[len(offsets) - 1]

    monkeypatch.setattr(requests, "get", fake_get)

    catalog = dtm_gsi._download_catalog()

    assert offsets == ["0", "1"]
    assert [f["attributes"]["DATA_NAME"] for f in catalog["features"]] == ["A", "B"]


def test_download_catalog_rejects_a_malformed_or_empty_catalogue(
        monkeypatch: pytest.MonkeyPatch) -> None:
    broken = requests.Response()
    broken.status_code = 200
    broken._content = json.dumps({"features": "not-a-list"}).encode()
    monkeypatch.setattr(requests, "get", lambda *a, **k: broken)
    with pytest.raises(RuntimeError, match="no feature list"):
        dtm_gsi._download_catalog()

    monkeypatch.setattr(requests, "get", lambda *a, **k: _page([]))
    with pytest.raises(RuntimeError, match="no LiDAR archives"):
        dtm_gsi._download_catalog()


def test_intersects_accepts_both_arcgis_rings_and_plain_geojson() -> None:
    bbox = (504_000, 704_000, 506_000, 706_000)
    assert dtm_gsi._intersects(_arcgis_feature(), bbox) is True
    assert dtm_gsi._intersects({}, bbox) is False

    # A GeoJSON geometry has no "rings", so it is compared in lon/lat instead.
    # (504000, 704000)-(506000, 706000) in Irish TM is ~9.4W, 53.08N.
    lonlat = {"geometry": {"type": "Polygon",
                           "coordinates": [[[-9.5, 53.0], [-9.3, 53.0],
                                            [-9.3, 53.2], [-9.5, 53.2],
                                            [-9.5, 53.0]]]}}
    assert dtm_gsi._intersects(lonlat, bbox) is True


def test_properties_reads_geojson_and_arcgis_feature_shapes() -> None:
    assert dtm_gsi._properties(_arcgis_feature())["DATA_NAME"] == "P_602766"
    assert dtm_gsi._properties({"properties": {"DATA_NAME": 7}}) == {"DATA_NAME": "7"}
    assert dtm_gsi._properties({}) == {}


def test_download_retries_then_succeeds(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    attempts = 0

    class _Stream:
        def __enter__(self) -> "_Stream":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def raise_for_status(self) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise requests.ConnectionError("flaky")

        def iter_content(self, _size: int) -> list[bytes]:
            return [b"payload", b""]

    monkeypatch.setattr(time, "sleep", lambda _s: None)
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Stream())

    dtm_gsi._download("https://x/a.7z", tmp_path / "a.7z")

    assert attempts == 2
    assert (tmp_path / "a.7z").read_bytes() == b"payload"


def test_download_gives_up_after_the_last_attempt(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def always_fail(*_a: object, **_k: object) -> None:
        raise requests.ConnectionError("down")

    monkeypatch.setattr(time, "sleep", lambda _s: None)
    monkeypatch.setattr(requests, "get", always_fail)

    with pytest.raises(requests.ConnectionError):
        dtm_gsi._download("https://x/a.7z", tmp_path / "a.7z")
    assert not (tmp_path / "a.7z").exists()


def _write_1m_dtm(path: Path) -> None:
    data = np.arange(100, dtype="float32").reshape(10, 10)
    with rasterio.open(path, "w", driver="GTiff", width=10, height=10, count=1,
                       dtype="float32", crs="EPSG:2157", nodata=NODATA,
                       transform=from_origin(500_000, 700_010, 1.0, 1.0)) as out:
        out.write(data, 1)


def test_resample_averages_one_metre_input_onto_the_five_metre_grid(
        tmp_path: Path) -> None:
    raw = tmp_path / "raw.tif"
    _write_1m_dtm(raw)

    dtm_gsi._resample(raw, tmp_path / "out.tif")

    with rasterio.open(tmp_path / "out.tif") as result:
        assert (result.width, result.height) == (2, 2)
        assert result.res == (5.0, 5.0)
        assert result.nodata == NODATA
        # Mean of the top-left 5x5 block of arange(100) reshaped 10x10.
        assert result.read(1)[0][0] == pytest.approx(22.0)
    assert not (tmp_path / "out.part").exists()


def test_materialize_downloads_extracts_and_resamples_once(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runs: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> None:
        runs.append(cmd)
        extracted = Path(cmd[2][2:]) / "nested"
        extracted.mkdir(parents=True, exist_ok=True)
        _write_1m_dtm(extracted / "dtm.tif")

    monkeypatch.setattr(dtm_gsi, "_download",
                        lambda _url, path: path.write_bytes(b"7z"))
    monkeypatch.setattr(subprocess, "run", fake_run)

    dest = dtm_gsi._materialize("https://x/a.7z", "P_1", tmp_path)

    assert dest == tmp_path / "P_1.tif"
    with rasterio.open(dest) as result:
        assert result.res == (5.0, 5.0)
    # The archive and its extraction scratch are removed; only the 5 m tif stays.
    assert not (tmp_path / "P_1.7z.part").exists()
    assert not (tmp_path / "P_1.raw").exists()

    # A second call is served from the cache without shelling out again.
    assert dtm_gsi._materialize("https://x/a.7z", "P_1", tmp_path) == dest
    assert len(runs) == 1


def test_materialize_cleans_up_scratch_when_extraction_fails(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(cmd: list[str], **_kwargs: object) -> None:
        Path(cmd[2][2:]).joinpath("junk.txt").write_text("partial")
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(dtm_gsi, "_download",
                        lambda _url, path: path.write_bytes(b"7z"))
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        dtm_gsi._materialize("https://x/a.7z", "P_2", tmp_path)

    assert not (tmp_path / "P_2.raw").exists()
    assert not (tmp_path / "P_2.7z.part").exists()


def test_fetch_scopes_the_catalogue_root_and_restores_it(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[Path | None] = []

    def record(*_args: object) -> list[Path]:
        seen.append(dtm_gsi._CATALOG_ROOT)
        return []

    monkeypatch.setattr(dtm_gsi, "_CATALOG_ROOT", None)
    monkeypatch.setattr(dtm_gsi, "fetch_gsi_lidar", record)

    assert dtm_gsi.fetch((0, 0, 1, 1), tmp_path / "tiles", tmp_path,
                         "EPSG:2157") == []

    assert seen == [tmp_path / "gsi-lidar-1m"]
    assert dtm_gsi._CATALOG_ROOT is None   # restored for the next chunk


def test_fetch_requires_a_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires cache_dir"):
        dtm_gsi.fetch((0, 0, 1, 1), tmp_path, None, "EPSG:2157")


def test_ireland_chunk_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.chunk.ireland.main.main") as entry:
        runpy.run_module("highliner.etls.chunk.ireland.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
