from dataclasses import dataclass


@dataclass(frozen=True)
class Anchor:
    x: float
    y: float
    elev: float
    sectors: tuple  # ((start_deg, end_deg, max_drop), ...)
