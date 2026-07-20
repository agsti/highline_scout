from pathlib import Path

import pytest
import requests

from highliner.etls.chunk import dtm_core
from highliner.etls.chunk.spain import dtm_icgc


def _http_error(status: int, retry_after: str | None = None) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    if retry_after is not None:
        resp.headers["Retry-After"] = retry_after
    return requests.HTTPError(response=resp)


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


def test_icgc_fetch_skips_failures(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path) -> Path:
        if int(bbox[0]) == 484000:           # simulate out-of-coverage column
            raise RuntimeError("ICGC WCS did not return ArcGrid data")
        return _fake_asc(bbox, width, height, dest)
    monkeypatch.setattr(dtm_icgc, "_download_tile", fake_download)

    paths = dtm_icgc.fetch((484000, 4646000, 486000, 4647500),
                           tmp_path / "tiles", tmp_path / "cache", "EPSG:25831")
    assert len(paths) == 4                    # 2 of 6 specs failed
    assert all(p.exists() for p in paths)


def test_icgc_fetch_retries_rate_limited_tiles_honoring_retry_after(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep",
                        lambda s: sleeps.append(s))
    attempts: dict[tuple[float, float, float, float], int] = {}

    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path) -> Path:
        n = attempts.get(bbox, 0) + 1
        attempts[bbox] = n
        if int(bbox[0]) == 484000 and n <= 2:     # first column throttled twice
            raise _http_error(429, retry_after="7")
        return _fake_asc(bbox, width, height, dest)

    monkeypatch.setattr(dtm_icgc, "_download_tile", fake_download)
    paths = dtm_icgc.fetch((484000, 4646000, 486000, 4647500),
                           tmp_path / "tiles", tmp_path / "cache", "EPSG:25831")

    assert len(paths) == 6                        # no tile silently dropped
    assert all(p.exists() for p in paths)
    assert max(attempts.values()) == 3            # 2 throttled tries + success
    assert sleeps.count(7.0) == 4                 # Retry-After honored (2 tiles x 2)


def test_icgc_fetch_raises_when_rate_limit_persists(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda s: None)

    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path) -> Path:
        raise _http_error(429)

    monkeypatch.setattr(dtm_icgc, "_download_tile", fake_download)
    with pytest.raises(requests.HTTPError):
        dtm_icgc.fetch((484000, 4646000, 486000, 4647500),
                       tmp_path / "tiles", tmp_path / "cache", "EPSG:25831")


def test_icgc_fetch_downloads_concurrently_in_spec_order(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    import time

    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path) -> Path:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return _fake_asc(bbox, width, height, dest)

    monkeypatch.setattr(dtm_icgc, "_download_tile", fake_download)
    bbox = (484000, 4646000, 486000, 4647500)
    paths = dtm_icgc.fetch(bbox, tmp_path / "tiles", tmp_path / "cache",
                           "EPSG:25831")

    expected = [tmp_path / "tiles" / f"t_{int(tb[0])}_{int(tb[1])}.asc"
                for tb, _w, _h in dtm_core.tile_specs(bbox, res=5.0, tile_px=175)]
    assert paths == expected                  # deterministic spec order
    assert peak >= 2, "tile downloads must overlap"


def test_icgc_fetch_downloads_into_tiles_dir(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spain's ICGC fetcher tiles the bbox and writes .asc into tiles_dir."""
    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path) -> Path:
        dest.write_text("tile")
        return dest

    monkeypatch.setattr(dtm_icgc, "_download_tile", fake_download)
    paths = dtm_icgc.fetch((484000.0, 4646000.0, 486000.0, 4647500.0),
                           tmp_path / "tiles", tmp_path / "cache",
                           "EPSG:25831")

    assert paths and all(p.suffix == ".asc" for p in paths)
    assert all(p.parent == tmp_path / "tiles" for p in paths)
