import os
from pathlib import Path

from highliner.etl.repositories.candidates import save_candidates
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate, PairFilter
from highliner.server.repositories import partition_cache as pc


def _cand(x: float, exposure: float) -> Candidate:
    a = Anchor(x=x, y=0.0, elev=100.0, sectors=())
    b = Anchor(x=x + 40.0, y=0.0, elev=100.0, sectors=())
    return Candidate(a=a, b=b, length=40.0, exposure=exposure, height_diff=0.0)


def test_to_candidates_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "q.parquet"
    save_candidates([_cand(10.0, 60.0)], p)
    got = pc.read_pair_columns(p).to_candidates()
    assert len(got) == 1
    c = got[0]
    assert (c.a.x, c.b.x, c.length, c.exposure) == (10.0, 50.0, 40.0, 60.0)


def test_select_masks_bbox_and_filter(tmp_path: Path) -> None:
    p = tmp_path / "q.parquet"
    save_candidates([_cand(10.0, 60.0), _cand(10.0, 15.0), _cand(9000.0, 60.0)], p)
    cols = pc.read_pair_columns(p)
    pf = PairFilter(min_len=0.0, max_len=1e9, min_exposure=30.0, max_dh=1e9)
    got = cols.select((0.0, -10.0, 100.0, 10.0), pf)
    # only the in-bbox, high-exposure pair survives
    assert [round(c.a.x) for c in got] == [10]


def test_empty_partition(tmp_path: Path) -> None:
    p = tmp_path / "q.parquet"
    save_candidates([], p)
    assert pc.read_pair_columns(p).to_candidates() == []


def test_cache_hit_and_mtime_invalidation(tmp_path: Path) -> None:
    p = tmp_path / "q.parquet"
    save_candidates([_cand(10.0, 60.0)], p)
    first = pc.pair_columns(p)
    assert pc.pair_columns(p) is first  # warm hit returns the cached object

    # Rewrite the partition and push its mtime forward: the changed key must
    # force a fresh read rather than serve the stale cached columns.
    save_candidates([_cand(20.0, 60.0), _cand(30.0, 60.0)], p)
    os.utime(p, (os.stat(p).st_mtime + 10.0, os.stat(p).st_mtime + 10.0))
    second = pc.pair_columns(p)
    assert second is not first
    assert len(second.length) == 2
