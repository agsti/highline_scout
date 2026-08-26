"""Tests for the Hong Kong Lands Department DTM source."""

import time
import zipfile
from pathlib import Path
from typing import cast

import pytest
import requests


class _Response:
    """Minimal stand-in for a streamed ``requests`` response."""

    def __init__(self, chunks: list[bytes], status_code: int = 200) -> None:
        self.chunks = chunks
        self.status_code = status_code

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, _size: int) -> list[bytes]:
        return self.chunks


def _archive_bytes() -> bytes:
    return b"zip archive"


def test_download_promotes_a_complete_archive(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    payload = _archive_bytes()
    monkeypatch.setattr(dtm_landsd, "DTM_SIZE", len(payload))
    seen: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> _Response:
        seen.append({"url": url, **kwargs})
        return _Response([payload])

    monkeypatch.setattr(requests, "get", fake_get)
    dest = tmp_path / dtm_landsd.DTM_FILENAME
    dtm_landsd._download(dest)

    assert dest.read_bytes() == payload
    assert not dest.with_suffix(dest.suffix + ".part").exists()
    assert seen[0]["url"] == dtm_landsd.DTM_URL
    assert seen[0]["headers"] == {}


def test_download_resumes_a_partial_file_with_a_range_header(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    payload = _archive_bytes()
    monkeypatch.setattr(dtm_landsd, "DTM_SIZE", len(payload))
    dest = tmp_path / dtm_landsd.DTM_FILENAME
    part = dest.with_suffix(dest.suffix + ".part")
    part.write_bytes(payload[:4])
    seen: list[dict[str, str]] = []

    def fake_get(_url: str, **kwargs: object) -> _Response:
        seen.append(cast(dict[str, str], kwargs["headers"]))
        return _Response([payload[4:]], status_code=206)

    monkeypatch.setattr(requests, "get", fake_get)
    dtm_landsd._download(dest)

    assert seen == [{"Range": "bytes=4-"}]
    assert dest.read_bytes() == payload


def test_download_retries_after_a_network_error(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    payload = _archive_bytes()
    monkeypatch.setattr(dtm_landsd, "DTM_SIZE", len(payload))
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    attempts = 0

    def fake_get(_url: str, **_kwargs: object) -> _Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.ConnectionError("reset")
        return _Response([payload])

    monkeypatch.setattr(requests, "get", fake_get)
    dest = tmp_path / dtm_landsd.DTM_FILENAME
    dtm_landsd._download(dest)

    assert attempts == 2
    assert dest.read_bytes() == payload


def test_download_reraises_when_every_attempt_fails(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    def fake_get(_url: str, **_kwargs: object) -> _Response:
        raise requests.ConnectionError("reset")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(requests.ConnectionError):
        dtm_landsd._download(tmp_path / dtm_landsd.DTM_FILENAME)


def test_download_discards_a_short_archive_that_never_completes(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    monkeypatch.setattr(dtm_landsd, "DTM_SIZE", 999)
    monkeypatch.setattr(requests, "get",
                        lambda _url, **_kw: _Response([b"truncated"]))
    dest = tmp_path / dtm_landsd.DTM_FILENAME

    with pytest.raises(RuntimeError, match="999 bytes"):
        dtm_landsd._download(dest)

    assert not dest.exists()
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_extract_ascii_takes_the_single_grid_member(tmp_path: Path) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    archive = tmp_path / "Whole_HK_DTM_5m.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("readme.txt", b"ignored")
        bundle.writestr("Whole_HK_DTM_5m.ASC", b"ncols 2\nnrows 1\n")

    dest = dtm_landsd._extract_ascii(archive, tmp_path / "grid.asc")

    assert dest.read_bytes() == b"ncols 2\nnrows 1\n"
    assert not list(tmp_path.glob("*.part"))


def test_extract_ascii_reuses_an_already_extracted_grid(
        tmp_path: Path) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    dest = tmp_path / "grid.asc"
    dest.write_bytes(b"ncols 2\n")

    # The archive does not exist: reuse must not reopen it.
    assert dtm_landsd._extract_ascii(tmp_path / "missing.zip", dest) == dest
    assert dest.read_bytes() == b"ncols 2\n"


def test_fetch_requires_a_cache_dir(tmp_path: Path) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    with pytest.raises(ValueError, match="cache_dir"):
        dtm_landsd.fetch((0, 0, 1, 1), tmp_path, None, "EPSG:2326")


def test_fetch_downloads_once_then_extracts_the_grid(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    buffer = tmp_path / "source.zip"
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("Whole_HK_DTM_5m.asc", b"ncols 2\n")
    payload = buffer.read_bytes()
    monkeypatch.setattr(dtm_landsd, "DTM_SIZE", len(payload))
    downloads = 0

    def fake_get(_url: str, **_kwargs: object) -> _Response:
        nonlocal downloads
        downloads += 1
        return _Response([payload])

    monkeypatch.setattr(requests, "get", fake_get)
    cache_dir = tmp_path / "cache"

    first = dtm_landsd.fetch((790000, 790000, 800000, 800000),
                             tmp_path / "tiles", cache_dir, "EPSG:2326")
    second = dtm_landsd.fetch((790000, 790000, 800000, 800000),
                              tmp_path / "tiles", cache_dir, "EPSG:2326")

    assert first == second == [cache_dir / "landsd_dtm_5m" / "Whole_HK_DTM_5m.asc"]
    assert first[0].read_bytes() == b"ncols 2\n"
    assert downloads == 1
