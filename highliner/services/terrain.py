import math

import numpy as np

from highliner.models.anchor import Anchor
from highliner.models.raster import Raster

# Steep cells swept per batch: bounds the (cells, azimuths) scratch arrays to
# a few tens of MB on cliff-dense chunks.
_SWEEP_BLOCK_CELLS = 65536

# One candidate anchor before thinning: (x, y, elev, sectors, score).
_ThinPoint = tuple[float, float, float, tuple[tuple[float, float, float], ...], float]


def compute_slope(dtm: np.ndarray, res: float) -> np.ndarray:
    """Slope in degrees from an elevation grid (np.gradient based)."""
    dy, dx = np.gradient(dtm, res)
    rise = np.hypot(dx, dy)
    slope: np.ndarray = np.degrees(np.arctan(rise))
    return slope


def _azimuth_offsets(radius: float, n_azimuths: int
                     ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Azimuths (deg) and the (dx, dy) sampling offsets at ``radius``.
    Bearing convention: 0=N(+y), 90=E(+x)."""
    az = np.arange(n_azimuths) * (360.0 / n_azimuths)
    rad = np.radians(az)
    return az, radius * np.sin(rad), radius * np.cos(rad)


def _group_sectors(azimuths: np.ndarray, drops: np.ndarray, min_drop: float
                   ) -> tuple[tuple[float, float, float], ...]:
    """Group consecutive dropping azimuths (circularly) into sectors.
    Returns tuple of (start_deg, end_deg, max_drop)."""
    n = len(azimuths)
    step_deg = 360.0 / n
    flags = [bool(d >= min_drop) for d in drops]
    if not any(flags):
        return ()

    # if the whole circle drops, emit one full sector
    if all(flags):
        return ((0.0, 360.0 - step_deg, round(float(max(drops)), 2)),)

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
            max_drop = max(max_drop, float(drops[j % n]))
            j += 1
        sectors.append((float(azimuths[start]),
                        float(azimuths[(j - 1) % n]),
                        round(max_drop, 2)))
    return tuple(sectors)


def drop_sectors(raster: Raster, x: float, y: float, radius: float,  # noqa: PLR0913
                 n_azimuths: int, min_drop: float
                 ) -> tuple[tuple[float, float, float], ...]:
    """Sweep azimuths around (x, y); group consecutive dropping directions
    into sectors. Returns tuple of (start_deg, end_deg, max_drop)."""
    base = raster.value_at(x, y)
    if math.isnan(base):
        return ()
    az, dx, dy = _azimuth_offsets(radius, n_azimuths)
    far = raster.values_at(x + dx, y + dy)
    drops = np.where(np.isnan(far), 0.0, base - far)
    return _group_sectors(az, drops, min_drop)


def _thin(points: list[_ThinPoint], thin_dist: float) -> list[Anchor]:
    """Greedy non-max suppression by descending drop; keep points >= thin_dist
    apart. Spatial-hash grid with thin_dist cells: a conflicting kept point can
    only live in the 3x3 neighborhood, so each check is O(1) on average."""
    if not points:
        return []
    pts = sorted(points, key=lambda p: -p[4])  # p = (x, y, elev, sectors, score)
    cell = thin_dist if thin_dist > 0 else 1.0
    r2 = thin_dist * thin_dist
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    kept = []
    for x, y, elev, sectors, _score in pts:
        gx, gy = math.floor(x / cell), math.floor(y / cell)
        blocked = False
        for nx in (gx - 1, gx, gx + 1):
            for ny in (gy - 1, gy, gy + 1):
                if any((px - x) ** 2 + (py - y) ** 2 <= r2
                       for px, py in grid.get((nx, ny), ())):
                    blocked = True
                    break
            if blocked:
                break
        if blocked:
            continue
        kept.append(Anchor(x=x, y=y, elev=elev, sectors=sectors))
        grid.setdefault((gx, gy), []).append((x, y))
    return kept


def extract_anchors(raster: Raster, slope_min: float, radius: float,  # noqa: PLR0913
                    n_azimuths: int, min_sector_drop: float,
                    thin_dist: float) -> list[Anchor]:
    slope = compute_slope(raster.data, raster.res)
    steep = np.argwhere(slope >= slope_min)
    if steep.size == 0:
        return []

    # One batched sweep per block of steep cells x azimuths instead of a
    # Python loop of per-point raster lookups. Blocked so the (cells, azimuth)
    # scratch arrays stay small on cliff-dense chunks.
    rows = steep[:, 0].astype("float64") + 0.5
    cols = steep[:, 1].astype("float64") + 0.5
    t = raster.transform
    xs = t.a * cols + t.b * rows + t.c
    ys = t.d * cols + t.e * rows + t.f

    az, dx, dy = _azimuth_offsets(radius, n_azimuths)
    candidates = []
    block = _SWEEP_BLOCK_CELLS
    for off in range(0, len(xs), block):
        xb, yb = xs[off:off + block], ys[off:off + block]
        base = raster.values_at(xb, yb)
        far = raster.values_at(xb[:, None] + dx[None, :],
                               yb[:, None] + dy[None, :])
        drops = np.where(np.isnan(far), 0.0, base[:, None] - far)
        # NaN base compares False everywhere, so those cells never get flagged.
        for i in np.flatnonzero((drops >= min_sector_drop).any(axis=1)):
            sectors = _group_sectors(az, drops[i], min_sector_drop)
            if not sectors:
                continue
            best_drop = max(s[2] for s in sectors)
            candidates.append((float(xb[i]), float(yb[i]), float(base[i]),
                               sectors, best_drop))
    return _thin(candidates, thin_dist)
