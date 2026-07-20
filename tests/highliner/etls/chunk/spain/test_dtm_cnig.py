from pathlib import Path
from typing import cast

import pytest
import requests

from highliner.etls.chunk import dtm as ingest
from highliner.etls.chunk.spain import dtm_cnig


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


def test_cnig_request_retries_throttle_then_succeeds(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.spain.dtm_cnig.time.sleep",
                        lambda s: sleeps.append(s))
    responses = [_response(429, retry_after="9"), _response(200)]

    class FakeSession:
        def request(self, method: str, url: str, **kwargs: object) -> requests.Response:
            return responses.pop(0)

    resp = dtm_cnig._cnig_request(cast(requests.Session, FakeSession()), "GET", "http://x")
    assert resp.status_code == 200
    assert sleeps == [9.0]                 # Retry-After honored, slept once


def test_cnig_request_returns_last_response_when_throttle_persists(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("highliner.etls.chunk.spain.dtm_cnig.time.sleep",
                        lambda s: None)

    class FakeSession:
        def request(self, method: str, url: str, **kwargs: object) -> requests.Response:
            return _response(429)

    resp = dtm_cnig._cnig_request(cast(requests.Session, FakeSession()), "GET", "http://x")
    assert resp.status_code == 429         # caller then raises via raise_for_status


def test_cnig_query_sheets_retries_throttled_page(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.spain.dtm_cnig.time.sleep",
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

    out = dtm_cnig._cnig_query_sheets(
        cast(requests.Session, FakeSession()),
        (400000.0, 4600000.0, 410000.0, 4610000.0), "EPSG:25830")
    assert out == [("42", "PNOA-MDT05-H30-0500-COG.tif")]
    assert sleeps == [3.0]


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

    monkeypatch.setattr(dtm_cnig, "_download_idee_tile", fake_download)

    paths = ingest.fetch_tiles((188000, 3060000, 188500, 3060500),
                               tmp_path / "tiles", source="idee",
                               crs="EPSG:4083")
    assert paths
    assert all(p.suffix == ".tif" for p in paths)
    assert {c[4] for c in calls} == {"EPSG:4083"}


def test_fetch_tiles_cnig_uses_explicit_cache_dir(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Path] = []

    monkeypatch.setattr(dtm_cnig, "_cnig_query_sheets",
                        lambda *a, **k: [("sec", "sheet.tif")])

    def fake_download(session: object, sec: str, filename: str, dest: Path) -> Path:
        seen.append(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake")
        return dest

    monkeypatch.setattr(dtm_cnig, "_download_cnig_sheet", fake_download)

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
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda s: None)
    monkeypatch.setattr(dtm_cnig, "_cnig_query_sheets",
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

    monkeypatch.setattr(dtm_cnig, "_download_cnig_sheet", fake_download)

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
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda s: None)
    monkeypatch.setattr(dtm_cnig, "_cnig_query_sheets",
                        lambda *a, **k: [("sec", "sheet.tif")])

    def fake_download(session: object, sec: str, filename: str, dest: Path) -> Path:
        raise requests.exceptions.ChunkedEncodingError("Connection broken")

    monkeypatch.setattr(dtm_cnig, "_download_cnig_sheet", fake_download)

    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        ingest.fetch_tiles(
            (188000, 3060000, 198000, 3070000),
            tmp_path / "data" / "spain" / "canarias" / "tiles" / "chunk_0_0_123",
            source="cnig",
            crs="EPSG:4083",
            cache_dir=tmp_path / "cache" / "spain",
        )


def test_cached_query_sheets_caches_result(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[float, ...], str]] = []

    def fake_query(session: object, bbox: tuple[float, ...],
                   crs: str) -> list[tuple[str, str]]:
        calls.append((bbox, crs))
        return [("42", "sheet.tif")]

    monkeypatch.setattr(dtm_cnig, "_cnig_query_sheets", fake_query)
    cache_dir = tmp_path / "idx"
    bbox = (400000.0, 4600000.0, 410000.0, 4610000.0)

    session = cast(requests.Session, None)
    a = dtm_cnig._cached_query_sheets(session, bbox, "EPSG:25830", cache_dir)
    b = dtm_cnig._cached_query_sheets(session, bbox, "EPSG:25830", cache_dir)

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

    monkeypatch.setattr(dtm_cnig, "_cnig_query_sheets", fake_query)
    cache_dir = tmp_path / "idx"
    bbox = (0.0, 0.0, 10.0, 10.0)

    session = cast(requests.Session, None)
    assert dtm_cnig._cached_query_sheets(session, bbox, "EPSG:25830", cache_dir) == []
    assert dtm_cnig._cached_query_sheets(session, bbox, "EPSG:25830", cache_dir) == []
    assert len(calls) == 1                       # empty result cached too


def test_cnig_fetch_delegates_to_cache_client(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The CNIG fetcher forwards (bbox, cache_dir, crs) and ignores tiles_dir."""
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, cache_root: object, crs: object) -> list[Path]:
        seen.append((bbox, cache_root, crs))
        return [tmp_path / "sheet.tif"]

    monkeypatch.setattr(dtm_cnig, "_fetch_cnig_tiles", fake)
    out = dtm_cnig.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                         tmp_path / "cache", "EPSG:25830")

    assert out == [tmp_path / "sheet.tif"]
    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "cache", "EPSG:25830")]


def test_cnig_fetch_requires_cache_dir(tmp_path: Path) -> None:
    """Without a cache dir the source fails loudly rather than writing holes."""
    with pytest.raises(ValueError, match="cnig source requires cache_dir"):
        dtm_cnig.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                       "EPSG:25830")


def test_idee_fetch_passes_crs_to_each_tile_download(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """IDEE is a coverage API: each tile download gets the region CRS."""
    seen_crs: list[str] = []

    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path, crs: str) -> Path:
        seen_crs.append(crs)
        dest.write_text("tile")
        return dest

    monkeypatch.setattr(dtm_cnig, "_download_idee_tile", fake_download)
    paths = dtm_cnig.fetch_idee((484000.0, 4646000.0, 486000.0, 4647500.0),
                                tmp_path / "tiles", tmp_path / "cache",
                                "EPSG:25830")

    assert paths and all(p.suffix == ".tif" for p in paths)
    assert set(seen_crs) == {"EPSG:25830"}
