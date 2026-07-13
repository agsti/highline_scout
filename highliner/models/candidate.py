from dataclasses import dataclass

from highliner.models.anchor import Anchor


@dataclass(frozen=True)
class Candidate:
    a: Anchor
    b: Anchor
    length: float
    exposure: float
    height_diff: float


@dataclass(frozen=True)
class PairFilter:
    """Live slider thresholds that narrow precomputed candidates at serve time.

    Applied as a vectorized mask over a partition's columns before any
    ``Candidate`` object is built, so only surviving pairs cross into Python.
    """
    min_len: float
    max_len: float
    min_exposure: float
    max_dh: float
