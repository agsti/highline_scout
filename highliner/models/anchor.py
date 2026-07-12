from dataclasses import dataclass


@dataclass(frozen=True)
class Anchor:
    x: float
    y: float
    elev: float
    # each sector is (start_deg, end_deg, max_drop)
    sectors: tuple[tuple[float, float, float], ...]
