import numpy as np
from scipy.spatial import cKDTree

from highliner.core import config, geo
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.models.raster import Raster

# Profile samples gathered per batch: bounds the flattened sampling arrays to
# a few tens of MB on pair-dense chunks.
_PROFILE_BLOCK_SAMPLES = 2_000_000

# Raw KD-tree pairs pre-filtered per batch: bounds the derived per-pair arrays
# (lengths, bearings, ...) to a few tens of MB. Cliff-dense alpine chunks
# produce tens of millions of raw pairs; deriving them all at once costs
# ~90 bytes per pair (multi-GB per worker, OOM at 8 workers).
_PREFILTER_BLOCK_PAIRS = 1_000_000


def _profile_lows(raster: Raster, x1: np.ndarray, y1: np.ndarray,  # noqa: PLR0913
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


def find_candidates(  # noqa: PLR0913
        anchors: list[Anchor], raster: Raster, max_len: float,
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
    # Sort (i asc, j asc) by packing each pair into one uint64 key sorted in
    # place (anchor indices are far below 2**32). Compared to lexsort + take
    # this keeps the transient under query_pairs' own ~32 B/pair internals on
    # pair-dense chunks, and scalar sort is much faster than a record sort.
    # Built with in-place ops (and bit-level views of the index columns) so at
    # most one extra 8 B/pair array exists at a time.
    key = pairs[:, 0].astype(np.uint64)
    key <<= np.uint64(32)
    key |= pairs[:, 1].view(np.uint64)
    key.sort()
    pairs[:, 0] = key >> np.uint64(32)
    key &= np.uint64(0xFFFFFFFF)
    pairs[:, 1] = key
    del key

    # Pre-filter one block of raw pairs at a time; only survivors (typically
    # ~1% on dense chunks) persist across blocks, in the same sorted order.
    si_parts, sj_parts, len_parts, dh_parts = [], [], [], []
    for off in range(0, len(pairs), _PREFILTER_BLOCK_PAIRS):
        pi = pairs[off:off + _PREFILTER_BLOCK_PAIRS, 0]
        pj = pairs[off:off + _PREFILTER_BLOCK_PAIRS, 1]
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
                           anchors[pj[k]].sectors, sector_tol)],
                      dtype=np.int64)
        if ks.size:
            si_parts.append(pi[ks])
            sj_parts.append(pj[ks])
            len_parts.append(lengths[ks])
            dh_parts.append(dhs[ks])
    if not si_parts:
        return []
    si = np.concatenate(si_parts)
    sj = np.concatenate(sj_parts)
    lengths = np.concatenate(len_parts)
    dhs = np.concatenate(dh_parts)

    ns = np.maximum(2, (lengths / raster.res).astype(np.int64) + 1)
    lows = np.empty(len(si))
    # Block by total sample count so the flattened profile arrays stay small
    # even on chunks with hundreds of thousands of surviving pairs.
    bounds = np.searchsorted(np.cumsum(ns), np.arange(
        _PROFILE_BLOCK_SAMPLES, int(ns.sum()), _PROFILE_BLOCK_SAMPLES), side="left") + 1
    for lo, hi in zip(np.r_[0, bounds], np.r_[bounds, len(si)], strict=True):
        if lo >= hi:
            continue
        lows[lo:hi] = _profile_lows(raster,
                                    coords[si[lo:hi], 0], coords[si[lo:hi], 1],
                                    coords[sj[lo:hi], 0], coords[sj[lo:hi], 1],
                                    ns[lo:hi])
    exposures = np.minimum(elevs[si], elevs[sj]) - lows

    out = []
    for m in np.flatnonzero(~np.isnan(lows) & (exposures >= min_exposure)):
        a, b = anchors[si[m]], anchors[sj[m]]
        out.append(Candidate(a=a, b=b, length=round(float(lengths[m]), 1),
                             exposure=round(float(exposures[m]), 1),
                             height_diff=round(float(dhs[m]), 1)))
    return out
