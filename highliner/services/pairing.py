import numpy as np
from scipy.spatial import cKDTree

from highliner.core import config, geo
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.models.raster import Raster

# Profile samples gathered per batch: bounds the flattened sampling arrays to
# a few tens of MB on pair-dense chunks.
_PROFILE_BLOCK_SAMPLES = 2_000_000


def filter_candidates(candidates: list[Candidate], max_len: float, min_len: float,
                      min_exposure: float, max_dh: float) -> list[Candidate]:
    """Narrow precomputed candidates by the live slider thresholds."""
    return [c for c in candidates
            if min_len <= c.length <= max_len
            and c.exposure >= min_exposure
            and c.height_diff <= max_dh]


def _profile_lows(raster: Raster, x1: np.ndarray, y1: np.ndarray,
                  x2: np.ndarray, y2: np.ndarray, ns: np.ndarray) -> np.ndarray:
    """NaN-aware interior minimum of the elevation profile of each segment
    (endpoints excluded), all segments sampled in one raster gather.

    Sample positions replicate ``np.linspace(p1, p2, n)`` bitwise: offsets are
    ``i * ((p2 - p1) / (n - 1))`` with the final sample forced to ``p2``.
    Segments with no interior samples (n <= 2) come back NaN, matching
    ``_interior_min`` on a 2-point profile.
    """
    seg_end = np.cumsum(ns)
    seg_start = seg_end - ns
    seg_id = np.repeat(np.arange(len(ns)), ns)
    tpos = np.arange(int(seg_end[-1])) - seg_start[seg_id]

    div = ns - 1
    step_x = (x2 - x1) / div
    step_y = (y2 - y1) / div
    xs = tpos * step_x[seg_id] + x1[seg_id]
    ys = tpos * step_y[seg_id] + y1[seg_id]
    last = seg_end - 1
    xs[last] = x2
    ys[last] = y2
    vals = raster.values_at(xs, ys)

    lows = np.full(len(ns), np.nan)
    good = ns >= 3
    if good.any():
        s = (seg_start + 1)[good]
        e = (seg_end - 1)[good]
        idx = np.empty(2 * s.size, dtype=np.int64)
        idx[0::2] = s
        idx[1::2] = e
        # even entries of reduceat cover [s_k, e_k) = the interior samples;
        # fmin skips NaNs so an all-NaN interior stays NaN
        lows[good] = np.fmin.reduceat(vals, idx)[0::2]
    return lows


def find_candidates(anchors: list[Anchor], raster: Raster, max_len: float,
                    min_len: float, min_exposure: float, max_dh: float,
                    sector_tol: float = config.SECTOR_TOL_DEG) -> list[Candidate]:
    if len(anchors) < 2:
        return []
    coords = np.array([[a.x, a.y] for a in anchors])
    elevs = np.array([a.elev for a in anchors], dtype="float64")
    tree = cKDTree(coords)
    pairs = tree.query_pairs(max_len, output_type="ndarray")
    if pairs.size == 0:
        return []
    pairs = pairs[np.lexsort((pairs[:, 1], pairs[:, 0]))]
    pi, pj = pairs[:, 0], pairs[:, 1]

    dx = coords[pj, 0] - coords[pi, 0]
    dy = coords[pj, 1] - coords[pi, 1]
    lengths = np.hypot(dx, dy)
    dhs = np.abs(elevs[pi] - elevs[pj])
    cheap = (lengths >= min_len) & (lengths <= max_len) & (dhs <= max_dh)

    bearings = np.degrees(np.arctan2(dx, dy)) % 360.0
    ks = np.array([k for k in np.flatnonzero(cheap)
                   if geo.bearing_in_sectors(
                       float(bearings[k]), anchors[pi[k]].sectors, sector_tol)
                   and geo.bearing_in_sectors(
                       (float(bearings[k]) + 180.0) % 360.0,
                       anchors[pj[k]].sectors, sector_tol)])
    if ks.size == 0:
        return []

    ns = np.maximum(2, (lengths[ks] / raster.res).astype(np.int64) + 1)
    lows = np.empty(len(ks))
    # Block by total sample count so the flattened profile arrays stay small
    # even on chunks with hundreds of thousands of surviving pairs.
    bounds = np.searchsorted(np.cumsum(ns), np.arange(
        _PROFILE_BLOCK_SAMPLES, int(ns.sum()), _PROFILE_BLOCK_SAMPLES), side="left") + 1
    for lo, hi in zip(np.r_[0, bounds], np.r_[bounds, len(ks)], strict=True):
        if lo >= hi:
            continue
        kb = ks[lo:hi]
        lows[lo:hi] = _profile_lows(raster,
                                    coords[pi[kb], 0], coords[pi[kb], 1],
                                    coords[pj[kb], 0], coords[pj[kb], 1],
                                    ns[lo:hi])
    exposures = np.minimum(elevs[pi[ks]], elevs[pj[ks]]) - lows

    out = []
    for m in np.flatnonzero(~np.isnan(lows) & (exposures >= min_exposure)):
        k = ks[m]
        a, b = anchors[pi[k]], anchors[pj[k]]
        out.append(Candidate(a=a, b=b, length=round(float(lengths[k]), 1),
                             exposure=round(float(exposures[m]), 1),
                             height_diff=round(float(dhs[k]), 1)))
    return out
