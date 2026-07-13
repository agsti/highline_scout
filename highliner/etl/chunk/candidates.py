"""Persist candidate pairs as parquet partitions (write side).

One row per pair: both endpoints (x, y, elev) plus the precomputed scalars the
serve-time slider filters need. Anchor sectors are not stored — the directional
check is baked in at precompute time and `build_zones` does not use sectors.

The read side (`load_candidates`) lives in
`highliner.server.repositories.candidates`.
"""
from pathlib import Path

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
