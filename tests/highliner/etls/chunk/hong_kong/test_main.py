from pathlib import Path
from typing import Any

import pytest


def test_hong_kong_chunk_adapter_uses_the_territory_dtm(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk.hong_kong import main as hong_kong

    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(hong_kong.shared, "precompute", fake)
    hong_kong.main(["--data-dir", "/tmp/data", "--cache-dir", "/tmp/cache"])

    assert calls[0]["args"][:2] == ("hong_kong", "hong_kong")
    assert calls[0]["crs"] == "EPSG:2326"
    assert calls[0]["dtm_source"] == "landsd_dtm_5m"
    assert calls[0]["workers"] == 1
    assert calls[0]["fetch"].__module__.endswith("dtm_landsd")
    assert hong_kong.REGION.bbox == (790000, 790000, 880000, 850000)


def test_hong_kong_dtm_reuses_a_complete_cached_archive(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    payload = b"zip archive"
    monkeypatch.setattr(dtm_landsd, "DTM_SIZE", len(payload))
    cached = tmp_path / "cache" / "landsd_dtm_5m" / dtm_landsd.DTM_FILENAME
    cached.parent.mkdir(parents=True)
    cached.write_bytes(payload)

    extracted = cached.with_suffix(".asc")
    monkeypatch.setattr(dtm_landsd, "_extract_ascii",
                        lambda _archive, _dest: extracted)
    out = dtm_landsd.fetch((790000, 790000, 800000, 800000), tmp_path / "tiles",
                           tmp_path / "cache", "EPSG:2326")

    assert out == [extracted]


def test_hong_kong_dtm_rejects_another_crs(tmp_path: Path) -> None:
    from highliner.etls.chunk.hong_kong import dtm_landsd

    with pytest.raises(ValueError, match="EPSG:2326"):
        dtm_landsd.fetch((0, 0, 1, 1), tmp_path, tmp_path, "EPSG:4326")


def test_hong_kong_chunk_rejects_a_non_positive_worker_count() -> None:
    from highliner.etls.chunk.hong_kong import main as hong_kong

    with pytest.raises(SystemExit, match=">= 1"):
        hong_kong.main(["--workers", "0"])


def test_hong_kong_chunk_skips_a_region_it_was_not_asked_for(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk.hong_kong import main as hong_kong

    def fail(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("precompute must not run for another region")

    monkeypatch.setattr(hong_kong.shared, "precompute", fail)

    hong_kong.main(["--only", "macau"])
