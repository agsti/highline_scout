from dataclasses import dataclass

from highliner.models.anchor import Anchor


@dataclass(frozen=True)
class Candidate:
    a: Anchor
    b: Anchor
    length: float
    exposure: float
    height_diff: float
