from collections import defaultdict
from collections.abc import Callable

import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import MultiPoint

from highliner.core import config, geo
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.models.zone import Zone


def _union_find(n: int) -> tuple[Callable[[int], int], Callable[[int, int], None]]:
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    return find, union


def build_zones(candidates: list[Candidate],
                cluster_dist: float = config.CLUSTER_DIST_M) -> list[Zone]:
    """Cluster the anchors of valid pairs into zones.

    Pair endpoints always join the same zone (merging both rims of a gap);
    additionally, any two paired anchors within `cluster_dist` are merged.
    """
    if not candidates:
        return []

    anchors: list[Anchor] = []  # unique anchors, in first-seen order
    index: dict[Anchor, int] = {}   # Anchor -> position in `anchors`
    for c in candidates:
        for a in (c.a, c.b):
            if a not in index:
                index[a] = len(anchors)
                anchors.append(a)

    find, union = _union_find(len(anchors))
    pair_idx = [(index[c.a], index[c.b]) for c in candidates]
    for i, j in pair_idx:
        union(i, j)
    coords = np.array([[a.x, a.y] for a in anchors])
    for i, j in cKDTree(coords).query_pairs(cluster_dist):
        union(i, j)

    members = defaultdict(list)     # component root -> anchor indices
    for i in range(len(anchors)):
        members[find(i)].append(i)
    comp_pairs = defaultdict(list)  # component root -> Candidates
    for c, (i, _j) in zip(candidates, pair_idx, strict=True):
        comp_pairs[find(i)].append(c)

    zones = []
    for root, idxs in members.items():
        pairs = comp_pairs[root]
        hull = MultiPoint([(anchors[i].x, anchors[i].y) for i in idxs]).convex_hull
        exposures = [p.exposure for p in pairs]
        lengths = [p.length for p in pairs]
        zones.append(Zone(
            polygon=hull.buffer(config.ZONE_BUFFER_M),
            height_min=min(exposures),
            height_max=max(exposures),
            length_min=min(lengths),
            length_max=max(lengths),
            n_anchors=len(idxs),
            n_pairs=len(pairs),
        ))
    return sorted(zones, key=lambda z: z.height_max, reverse=True)


def reproject_candidates(cands: list[Candidate], src_crs: str,
                         dst_crs: str) -> list[Candidate]:
    """Move each candidate's endpoints from ``src_crs`` into ``dst_crs``.

    A no-op when the CRSs match. Only x/y move; elevation, sectors, and the
    precomputed metric fields (length/exposure/height_diff) are invariants.
    """
    if src_crs == dst_crs or not cands:
        return cands
    xs = np.array([v for c in cands for v in (c.a.x, c.b.x)])
    ys = np.array([v for c in cands for v in (c.a.y, c.b.y)])
    tx, ty = geo.reproject_xy(xs, ys, src_crs, dst_crs)
    out: list[Candidate] = []
    for i, c in enumerate(cands):
        a = Anchor(x=float(tx[2 * i]), y=float(ty[2 * i]),
                   elev=c.a.elev, sectors=c.a.sectors)
        b = Anchor(x=float(tx[2 * i + 1]), y=float(ty[2 * i + 1]),
                   elev=c.b.elev, sectors=c.b.sectors)
        out.append(Candidate(a=a, b=b, length=c.length,
                             exposure=c.exposure, height_diff=c.height_diff))
    return out


def dedup_candidates(cands: list[Candidate],
                     grid_m: float = config.SEAM_DEDUP_GRID_M,
                     bearing_bucket_deg: float = config.SEAM_DEDUP_BEARING_DEG,
                     ) -> list[Candidate]:
    """Drop near-duplicate pairs by a (midpoint, length, bearing) signature.

    Endpoint order is canonicalized (sorted) so ``(a, b)`` and ``(b, a)`` — and
    the two overlapping regions' independent extractions of one line — collide.

    Known heuristic limitation: this is a grid-snap, not a true clustering, so
    a duplicate can dodge collapse if its endpoints are near-vertical (x1 ~= x2,
    where ``sorted()``'s tuple-order tiebreak on y can flip which endpoint is
    "first" between the two copies) or if the pair's midpoint/bearing sits
    right on a grid-cell or bearing-bucket boundary and rounds to different
    buckets in the two extractions. Either case only re-inflates a seam zone's
    ``n_pairs``/``n_anchors`` counts — it never produces wrong geometry, since
    the union-find in `build_zones` still merges the (near-identical) anchors
    into one component.
    """
    seen: set[tuple[int, int, int, int]] = set()
    out: list[Candidate] = []
    for c in cands:
        (x1, y1), (x2, y2) = sorted(((c.a.x, c.a.y), (c.b.x, c.b.y)))
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        brg = geo.bearing(x1, y1, x2, y2)
        key = (round(mx / grid_m), round(my / grid_m),
               round(c.length / grid_m), round(brg / bearing_bucket_deg))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out
