from pathlib import Path

import pytest
import requests

from highliner.etls.chunk import dtm as ingest
from highliner.etls.chunk.italy import dtm_hrdtm


def test_fetch_tiles_hrdtm_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cache_dir"):
        ingest.fetch_tiles(
            (6800000.0, 4900000.0, 6810000.0, 4910000.0),
            tmp_path / "tiles", source="hrdtm", crs="EPSG:6875")


def test_fetch_tiles_hrdtm_reuses_complete_cached_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"national geotiff"
    monkeypatch.setattr(dtm_hrdtm, "HRDTM_SIZE", len(payload))
    cached = tmp_path / "cache" / "italy" / "hrdtm5m" / dtm_hrdtm.HRDTM_FILENAME
    cached.parent.mkdir(parents=True)
    cached.write_bytes(payload)

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not hit the network for a cached file")

    monkeypatch.setattr("highliner.etls.chunk.italy.dtm_hrdtm.requests.get", boom)

    paths = ingest.fetch_tiles(
        (6800000.0, 4900000.0, 6810000.0, 4910000.0),
        tmp_path / "tiles", source="hrdtm", crs="EPSG:6875",
        cache_dir=tmp_path / "cache" / "italy")

    assert paths == [cached]


def test_hrdtm_download_raises_and_discards_truncated_part(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr(dtm_hrdtm, "HRDTM_SIZE", 10)
    monkeypatch.setattr("highliner.etls.chunk.italy.dtm_hrdtm.time.sleep",
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


@pytest.mark.parametrize(
    ("status", "existing", "expected"),
    [(206, b"01234", b"0123456789"), (200, b"stale", b"56789")],
)
def test_hrdtm_stream_appends_only_when_server_honors_range(
        status: int, existing: bytes, expected: bytes, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    part = tmp_path / "terrain.tif.part"
    part.write_bytes(existing)
    monkeypatch.setattr(dtm_hrdtm, "HRDTM_SIZE", 10)
    response = requests.Response()
    response.status_code = status
    response._content = b"56789"
    response._content_consumed = True  # type: ignore[attr-defined]
    seen_headers: list[dict[str, str]] = []

    def fake_get(url: str, headers: dict[str, str], stream: bool,
                 timeout: int) -> requests.Response:
        seen_headers.append(headers)
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    dtm_hrdtm._resume_stream(part)

    assert seen_headers == [{"Range": f"bytes={len(existing)}-"}]
    assert part.read_bytes() == expected


def test_hrdtm_complete_partial_file_does_not_request_again(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    part = tmp_path / "terrain.tif.part"
    part.write_bytes(b"complete")
    monkeypatch.setattr(dtm_hrdtm, "HRDTM_SIZE", len(part.read_bytes()))

    def fail(*args: object, **kwargs: object) -> requests.Response:
        raise AssertionError("a complete partial file must not be downloaded again")

    monkeypatch.setattr(requests, "get", fail)

    dtm_hrdtm._resume_stream(part)


def test_hrdtm_fetch_passes_only_the_cache_root(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HR-DTM is one national file: bbox and crs are irrelevant to the client."""
    seen: list[object] = []

    def fake(cache_root: object) -> list[Path]:
        seen.append(cache_root)
        return [tmp_path / "hrdtm.tif"]

    monkeypatch.setattr(dtm_hrdtm, "fetch_hrdtm", fake)
    out = dtm_hrdtm.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                          tmp_path / "cache", "EPSG:32632")

    assert out == [tmp_path / "hrdtm.tif"]
    assert seen == [tmp_path / "cache"]


def test_hrdtm_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="hrdtm source requires cache_dir"):
        dtm_hrdtm.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                        "EPSG:32632")
