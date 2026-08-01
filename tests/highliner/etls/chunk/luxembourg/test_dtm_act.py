from pathlib import Path

import pytest

from highliner.etls.chunk.luxembourg import dtm_act


def test_act_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cache_dir"):
        dtm_act.fetch((48_000, 56_000, 49_000, 57_000), tmp_path, None,
                      "EPSG:2169")


def test_act_fetch_reuses_cached_terrain_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cached = tmp_path / "act_mnt" / dtm_act.TERRAIN_FILENAME
    cached.parent.mkdir()
    cached.write_bytes(b"terrain")

    monkeypatch.setattr(dtm_act, "_complete", lambda path: path == cached)
    monkeypatch.setattr(dtm_act, "_install", lambda path: pytest.fail("network"))

    assert dtm_act.fetch((48_000, 56_000, 49_000, 57_000), tmp_path, tmp_path,
                         "EPSG:2169") == [cached]
