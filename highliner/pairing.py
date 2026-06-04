from dataclasses import dataclass
import numpy as np
from scipy.spatial import cKDTree
from highliner import config, geo
from highliner.raster import Raster
from highliner.anchors import Anchor


@dataclass(frozen=True)
class Candidate:
    a: Anchor
    b: Anchor
    length: float
    exposure: float
    height_diff: float


def _interior_min(profile: np.ndarray) -> float:
    """Lowest value strictly inside the profile (exclude the two endpoints)."""
    if profile.size <= 2:
        return float("nan")
    interior = profile[1:-1]
    interior = interior[~np.isnan(interior)]
    return float(np.min(interior)) if interior.size else float("nan")


def find_candidates(anchors, raster: Raster, max_len, min_len,
                    min_exposure, max_dh, sector_tol=config.SECTOR_TOL_DEG):
    if len(anchors) < 2:
        return []
    coords = np.array([[a.x, a.y] for a in anchors])
    tree = cKDTree(coords)
    seen = set()
    out = []
    for i, a in enumerate(anchors):
        for j in tree.query_ball_point(coords[i], max_len):
            if j <= i:
                continue
            b = anchors[j]
            key = (i, j)
            if key in seen:
                continue
            seen.add(key)

            length = float(np.hypot(b.x - a.x, b.y - a.y))
            if length < min_len or length > max_len:
                continue

            dh = abs(a.elev - b.elev)
            if dh > max_dh:
                continue

            ab = geo.bearing(a.x, a.y, b.x, b.y)
            ba = (ab + 180.0) % 360.0
            if not geo.bearing_in_sectors(ab, a.sectors, sector_tol):
                continue
            if not geo.bearing_in_sectors(ba, b.sectors, sector_tol):
                continue

            profile = raster.sample_line(a.x, a.y, b.x, b.y)
            low = _interior_min(profile)
            if np.isnan(low):
                continue
            exposure = min(a.elev, b.elev) - low
            if exposure < min_exposure:
                continue

            out.append(Candidate(a=a, b=b, length=round(length, 1),
                                 exposure=round(exposure, 1),
                                 height_diff=round(dh, 1)))
    return out
