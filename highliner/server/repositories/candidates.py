"""Read candidate pairs from parquet partitions (read side).

The write side (`save_candidates`) and the stored-column layout live in
`highliner.etl.repositories.candidates`.
"""
from pathlib import Path

from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate


def load_candidates(path: str | Path) -> list[Candidate]:
    import pandas as pd
    df = pd.read_parquet(path)
    out: list[Candidate] = []
    for r in df.itertuples(index=False):
        a = Anchor(x=float(r.ax), y=float(r.ay), elev=float(r.aelev), sectors=())
        b = Anchor(x=float(r.bx), y=float(r.by), elev=float(r.belev), sectors=())
        out.append(Candidate(a=a, b=b, length=float(r.length),
                             exposure=float(r.exposure),
                             height_diff=float(r.height_diff)))
    return out
