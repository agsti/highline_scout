from pathlib import Path

from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.repositories.candidates import load_candidates, save_candidates


def _cand() -> Candidate:
    a = Anchor(x=10.0, y=20.0, elev=100.0, sectors=())
    b = Anchor(x=40.0, y=20.0, elev=98.0, sectors=())
    return Candidate(a=a, b=b, length=30.0, exposure=55.0, height_diff=2.0)


def test_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "q.parquet"
    save_candidates([_cand()], p)
    got = load_candidates(p)
    assert len(got) == 1
    c = got[0]
    assert (c.a.x, c.a.y, c.a.elev) == (10.0, 20.0, 100.0)
    assert (c.b.x, c.b.y, c.b.elev) == (40.0, 20.0, 98.0)
    assert (c.length, c.exposure, c.height_diff) == (30.0, 55.0, 2.0)
    assert c.a.sectors == () and c.b.sectors == ()


def test_empty_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "q.parquet"
    save_candidates([], p)
    assert load_candidates(p) == []
