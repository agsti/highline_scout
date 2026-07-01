"""Persist candidate pairs as parquet partitions.

One row per pair: both endpoints (x, y, elev) plus the precomputed scalars the
serve-time slider filters need. Anchor sectors are not stored — the directional
check is baked in at precompute time and `build_zones` does not use sectors.
"""
from pathlib import Path

from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate

_COLS = ["ax", "ay", "aelev", "bx", "by", "belev",
         "length", "exposure", "height_diff"]


def save_candidates(candidates: list[Candidate], path: str | Path) -> None:
    import pandas as pd
    rows = [{
        "ax": c.a.x, "ay": c.a.y, "aelev": c.a.elev,
        "bx": c.b.x, "by": c.b.y, "belev": c.b.elev,
        "length": c.length, "exposure": c.exposure, "height_diff": c.height_diff,
    } for c in candidates]
    df = pd.DataFrame(rows, columns=_COLS)
    df.to_parquet(path)


def load_candidates(path: str | Path) -> list[Candidate]:
    import pandas as pd
    df = pd.read_parquet(path)
    out: list[Candidate] = []
    for r in df.itertuples(index=False):
        a = Anchor(x=float(r.ax), y=float(r.ay), elev=float(r.aelev), sectors=())
        b = Anchor(x=float(r.bx), y=float(r.by), elev=float(r.belev), sectors=())
        out.append(Candidate(a=a, b=b, length=float(r.length),
                             exposure=float(r.exposure), height_diff=float(r.height_diff)))
    return out
