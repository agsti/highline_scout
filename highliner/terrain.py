import math
import numpy as np
from highliner.raster import Raster
from highliner.anchors import Anchor


def compute_slope(dtm: np.ndarray, res: float) -> np.ndarray:
    """Slope in degrees from an elevation grid (np.gradient based)."""
    dy, dx = np.gradient(dtm, res)
    rise = np.hypot(dx, dy)
    return np.degrees(np.arctan(rise))


def drop_sectors(raster: Raster, x: float, y: float, radius: float,
                 n_azimuths: int, min_drop: float):
    """Sweep azimuths around (x, y); group consecutive dropping directions
    into sectors. Returns tuple of (start_deg, end_deg, max_drop)."""
    base = raster.value_at(x, y)
    if math.isnan(base):
        return ()
    step_deg = 360.0 / n_azimuths
    drops = []  # (azimuth, drop) for every sampled direction
    for i in range(n_azimuths):
        az = i * step_deg
        rad = math.radians(az)
        # bearing: 0=N(+y), 90=E(+x)
        tx = x + radius * math.sin(rad)
        ty = y + radius * math.cos(rad)
        far = raster.value_at(tx, ty)
        drop = 0.0 if math.isnan(far) else base - far
        drops.append((az, drop))

    flags = [d >= min_drop for _, d in drops]
    if not any(flags):
        return ()

    # if the whole circle drops, emit one full sector
    if all(flags):
        md = round(max(d for _, d in drops), 2)
        return ((0.0, 360.0 - step_deg, md),)

    # group consecutive azimuths (circularly) into sectors
    n = n_azimuths
    sectors = []
    visited = [False] * n
    for start in range(n):
        if not flags[start] or visited[start]:
            continue
        # only start a run at a rising edge (previous is False) to avoid splits
        if flags[(start - 1) % n]:
            continue
        j = start
        max_drop = 0.0
        while flags[j % n] and not visited[j % n]:
            visited[j % n] = True
            max_drop = max(max_drop, drops[j % n][1])
            j += 1
        sectors.append((drops[start][0],
                        drops[(j - 1) % n][0],
                        round(max_drop, 2)))
    return tuple(sectors)


def _thin(points, thin_dist):
    """Greedy non-max suppression by descending drop; keep points >= thin_dist apart."""
    from scipy.spatial import cKDTree
    if not points:
        return []
    pts = sorted(points, key=lambda p: -p[4])  # p = (x, y, elev, sectors, score)
    kept = []
    kept_xy = []
    for x, y, elev, sectors, _score in pts:
        if kept_xy:
            tree = cKDTree(kept_xy)
            if tree.query_ball_point([x, y], thin_dist):
                continue
        kept.append(Anchor(x=x, y=y, elev=elev, sectors=sectors))
        kept_xy.append([x, y])
    return kept


def extract_anchors(raster: Raster, slope_min: float, radius: float,
                    n_azimuths: int, min_sector_drop: float,
                    thin_dist: float) -> list[Anchor]:
    slope = compute_slope(raster.data, raster.res)
    steep = np.argwhere(slope >= slope_min)
    candidates = []
    for row, col in steep:
        x, y = raster.transform * (col + 0.5, row + 0.5)
        sectors = drop_sectors(raster, x, y, radius, n_azimuths, min_sector_drop)
        if not sectors:
            continue
        elev = raster.value_at(x, y)
        if np.isnan(elev):
            continue
        best_drop = max(s[2] for s in sectors)
        candidates.append((x, y, float(elev), sectors, best_drop))
    return _thin(candidates, thin_dist)
