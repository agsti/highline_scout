from pathlib import Path

import pytest
import requests

from highliner.etls.chunk import dtm as ingest
from highliner.etls.chunk import dtm_hrdtm


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

    monkeypatch.setattr("highliner.etls.chunk.dtm_hrdtm.requests.get", boom)

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
