from pathlib import Path
from typing import cast

import numpy as np
import pytest
import requests

from highliner.etls.chunk import dtm as ingest


def _http_error(status: int, retry_after: str | None = None) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    if retry_after is not None:
        resp.headers["Retry-After"] = retry_after
    return requests.HTTPError(response=resp)


def _response(status: int, retry_after: str | None = None,
              text: str = "") -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = text.encode()
    resp._content_consumed = True      # type: ignore[attr-defined]  # resp.close() no-op (no live socket)
    resp.encoding = "utf-8"
    if retry_after is not None:
        resp.headers["Retry-After"] = retry_after
    return resp


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


def test_cnig_request_retries_throttle_then_succeeds(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.dtm.time.sleep",
                        lambda s: sleeps.append(s))
    responses = [_response(429, retry_after="9"), _response(200)]

    class FakeSession:
        def request(self, method: str, url: str, **kwargs: object) -> requests.Response:
            return responses.pop(0)

    resp = ingest._cnig_request(cast(requests.Session, FakeSession()), "GET", "http://x")
    assert resp.status_code == 200
    assert sleeps == [9.0]                 # Retry-After honored, slept once


def test_cnig_request_returns_last_response_when_throttle_persists(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("highliner.etls.chunk.dtm.time.sleep", lambda s: None)

    class FakeSession:
        def request(self, method: str, url: str, **kwargs: object) -> requests.Response:
            return _response(429)

    resp = ingest._cnig_request(cast(requests.Session, FakeSession()), "GET", "http://x")
    assert resp.status_code == 429         # caller then raises via raise_for_status


def test_cnig_query_sheets_retries_throttled_page(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.dtm.time.sleep",
                        lambda s: sleeps.append(s))
    page1 = '<a href="detalleArchivo?sec=42">PNOA-MDT05-H30-0500-COG.tif</a>'
    responses = [
        _response(429, retry_after="3"),   # page 1 throttled once
        _response(200, text=page1),        # page 1 retried, one sheet
        _response(200, text=""),           # page 2 empty -> stop paginating
    ]

    class FakeSession:
        def request(self, method: str, url: str, **kwargs: object) -> requests.Response:
            return responses.pop(0)

    out = ingest._cnig_query_sheets(
        cast(requests.Session, FakeSession()),
        (400000.0, 4600000.0, 410000.0, 4610000.0), "EPSG:25830")
    assert out == [("42", "PNOA-MDT05-H30-0500-COG.tif")]
    assert sleeps == [3.0]


def test_tile_specs_covers_grid() -> None:
    specs = list(ingest.tile_specs((484000, 4646000, 486000, 4647500),
                                   res=5.0, tile_px=175))
    assert len(specs) == 6
    for _tb, w, h in specs:
        assert w > 0 and h > 0


def test_fetch_tiles_skips_failures(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_fetch_tiles_cnig_uses_explicit_cache_dir(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Path] = []

    monkeypatch.setattr(ingest, "_cnig_query_sheets",
                        lambda *a, **k: [("sec", "sheet.tif")])

    def fake_download(session: object, sec: str, filename: str, dest: Path) -> Path:
        seen.append(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake")
        return dest

    monkeypatch.setattr(ingest, "_download_cnig_sheet", fake_download)

    paths = ingest.fetch_tiles(
        (188000, 3060000, 198000, 3070000),
        tmp_path / "data" / "spain" / "canarias" / "tiles" / "chunk_0_0_123",
        source="cnig",
        crs="EPSG:4083",
        cache_dir=tmp_path / "cache" / "spain",
    )

    assert paths == [tmp_path / "cache" / "spain" / "mdt05_tiles" / "sheet.tif"]
    assert seen == paths


def test_fetch_tiles_cnig_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cache_dir"):
        ingest.fetch_tiles(
            (188000, 3060000, 198000, 3070000),
            tmp_path / "tiles", source="cnig", crs="EPSG:4083")


def test_fetch_cnig_tiles_retries_broken_stream_then_succeeds(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A CNIG download whose body stream drops mid-transfer (IncompleteRead ->
    # ChunkedEncodingError) must be retried, not abort the whole run.
    monkeypatch.setattr("highliner.etls.chunk.dtm.time.sleep", lambda s: None)
    monkeypatch.setattr(ingest, "_cnig_query_sheets",
                        lambda *a, **k: [("sec", "sheet.tif")])
    attempts = {"n": 0}

    def fake_download(session: object, sec: str, filename: str, dest: Path) -> Path:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise requests.exceptions.ChunkedEncodingError(
                "Connection broken: IncompleteRead(7328 bytes read, 856 more expected)")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake")
        return dest

    monkeypatch.setattr(ingest, "_download_cnig_sheet", fake_download)

    paths = ingest.fetch_tiles(
        (188000, 3060000, 198000, 3070000),
        tmp_path / "data" / "spain" / "canarias" / "tiles" / "chunk_0_0_123",
        source="cnig",
        crs="EPSG:4083",
        cache_dir=tmp_path / "cache" / "spain",
    )

    assert attempts["n"] == 2                     # retried once after the broken stream
    assert paths == [tmp_path / "cache" / "spain" / "mdt05_tiles" / "sheet.tif"]


def test_fetch_cnig_tiles_raises_when_broken_stream_persists(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("highliner.etls.chunk.dtm.time.sleep", lambda s: None)
    monkeypatch.setattr(ingest, "_cnig_query_sheets",
                        lambda *a, **k: [("sec", "sheet.tif")])

    def fake_download(session: object, sec: str, filename: str, dest: Path) -> Path:
        raise requests.exceptions.ChunkedEncodingError("Connection broken")

    monkeypatch.setattr(ingest, "_download_cnig_sheet", fake_download)

    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        ingest.fetch_tiles(
            (188000, 3060000, 198000, 3070000),
            tmp_path / "data" / "spain" / "canarias" / "tiles" / "chunk_0_0_123",
            source="cnig",
            crs="EPSG:4083",
            cache_dir=tmp_path / "cache" / "spain",
        )


def test_fetch_tiles_retries_rate_limited_tiles_honoring_retry_after(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.dtm.time.sleep",
                        lambda s: sleeps.append(s))
    attempts: dict[tuple[float, float, float, float], int] = {}

    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path) -> Path:
        n = attempts.get(bbox, 0) + 1
        attempts[bbox] = n
        if int(bbox[0]) == 484000 and n <= 2:     # first column throttled twice
            raise _http_error(429, retry_after="7")
        return _fake_asc(bbox, width, height, dest)

    monkeypatch.setattr(ingest, "_download_tile", fake_download)
    paths = ingest.fetch_tiles((484000, 4646000, 486000, 4647500),
                               tmp_path / "tiles", res=5.0, tile_px=175)

    assert len(paths) == 6                        # no tile silently dropped
    assert all(p.exists() for p in paths)
    assert max(attempts.values()) == 3            # 2 throttled tries + success
    assert sleeps.count(7.0) == 4                 # Retry-After honored (2 tiles x 2)


def test_fetch_tiles_raises_when_rate_limit_persists(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("highliner.etls.chunk.dtm.time.sleep", lambda s: None)

    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path) -> Path:
        raise _http_error(429)

    monkeypatch.setattr(ingest, "_download_tile", fake_download)
    with pytest.raises(requests.HTTPError):
        ingest.fetch_tiles((484000, 4646000, 486000, 4647500),
                           tmp_path / "tiles", res=5.0, tile_px=175)


def test_fetch_tiles_downloads_concurrently_in_spec_order(
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

    monkeypatch.setattr(ingest, "_download_tile", fake_download)
    bbox = (484000, 4646000, 486000, 4647500)
    paths = ingest.fetch_tiles(bbox, tmp_path / "tiles", res=5.0, tile_px=175)

    expected = [tmp_path / "tiles" / f"t_{int(tb[0])}_{int(tb[1])}.asc"
                for tb, _w, _h in ingest.tile_specs(bbox, res=5.0, tile_px=175)]
    assert paths == expected                  # deterministic spec order
    assert peak >= 2, "tile downloads must overlap"


def test_raster_from_tiles_merges(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_cached_query_sheets_caches_result(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[float, ...], str]] = []

    def fake_query(session: object, bbox: tuple[float, ...],
                   crs: str) -> list[tuple[str, str]]:
        calls.append((bbox, crs))
        return [("42", "sheet.tif")]

    monkeypatch.setattr(ingest, "_cnig_query_sheets", fake_query)
    cache_dir = tmp_path / "idx"
    bbox = (400000.0, 4600000.0, 410000.0, 4610000.0)

    session = cast(requests.Session, None)
    a = ingest._cached_query_sheets(session, bbox, "EPSG:25830", cache_dir)
    b = ingest._cached_query_sheets(session, bbox, "EPSG:25830", cache_dir)

    assert a == b == [("42", "sheet.tif")]
    assert len(calls) == 1                       # second call served from disk
    assert list(cache_dir.glob("*.json"))        # cache file written


def test_cached_query_sheets_caches_empty_result(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_query(session: object, bbox: tuple[float, ...],
                   crs: str) -> list[tuple[str, str]]:
        calls.append(1)
        return []

    monkeypatch.setattr(ingest, "_cnig_query_sheets", fake_query)
    cache_dir = tmp_path / "idx"
    bbox = (0.0, 0.0, 10.0, 10.0)

    session = cast(requests.Session, None)
    assert ingest._cached_query_sheets(session, bbox, "EPSG:25830", cache_dir) == []
    assert ingest._cached_query_sheets(session, bbox, "EPSG:25830", cache_dir) == []
    assert len(calls) == 1                       # empty result cached too


def test_fetch_tiles_hrdtm_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cache_dir"):
        ingest.fetch_tiles(
            (6800000.0, 4900000.0, 6810000.0, 4910000.0),
            tmp_path / "tiles", source="hrdtm", crs="EPSG:6875")


def test_fetch_tiles_hrdtm_reuses_complete_cached_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk import dtm_hrdtm

    payload = b"national geotiff"
    monkeypatch.setattr(dtm_hrdtm, "HRDTM_SIZE", len(payload))
    cached = tmp_path / "cache" / "italy" / "hrdtm5m" / dtm_hrdtm.HRDTM_FILENAME
    cached.parent.mkdir(parents=True)
    cached.write_bytes(payload)

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not hit the network for a cached file")

    monkeypatch.setattr("highliner.etls.chunk.dtm_hrdtm.requests.get", boom)

    paths = ingest.fetch_tiles(
        (6800000.0, 4900000.0, 6810000.0, 4910000.0),
        tmp_path / "tiles", source="hrdtm", crs="EPSG:6875",
        cache_dir=tmp_path / "cache" / "italy")

    assert paths == [cached]


def test_hrdtm_download_raises_and_discards_truncated_part(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk import dtm_hrdtm

    monkeypatch.setattr(dtm_hrdtm, "HRDTM_SIZE", 10)
    dest = tmp_path / dtm_hrdtm.HRDTM_FILENAME

    def fake_resume(part: Path) -> None:
        part.write_bytes(b"short")            # stream "completed" undersized

    monkeypatch.setattr(dtm_hrdtm, "_resume_stream", fake_resume)

    with pytest.raises(RuntimeError, match="expected 10"):
        dtm_hrdtm._download(dest)
    assert not dest.exists()
    assert not dest.with_suffix(".tif.part").exists()   # truncated part dropped


def test_hrdtm_download_resumes_broken_streams_until_complete(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk import dtm_hrdtm

    monkeypatch.setattr(dtm_hrdtm, "HRDTM_SIZE", 10)
    monkeypatch.setattr("highliner.etls.chunk.dtm_hrdtm.time.sleep",
                        lambda s: None)
    dest = tmp_path / dtm_hrdtm.HRDTM_FILENAME
    attempts = {"n": 0}

    def fake_resume(part: Path) -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            part.write_bytes(b"01234")        # connection drops mid-stream
            raise requests.exceptions.ChunkedEncodingError("broken")
        with part.open("ab") as fh:           # Range resume appends the rest
            fh.write(b"56789")

    monkeypatch.setattr(dtm_hrdtm, "_resume_stream", fake_resume)

    dtm_hrdtm._download(dest)

    assert attempts["n"] == 2
    assert dest.read_bytes() == b"0123456789"
