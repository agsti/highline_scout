from collections import defaultdict
from typing import Callable
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import MultiPoint
from highliner.core import config
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
    for c, (i, _j) in zip(candidates, pair_idx):
        comp_pairs[find(i)].append(c)

    zones = []
    for root, idxs in members.items():
        pairs = comp_pairs[root]
        hull = MultiPoint([(anchors[i].x, anchors[i].y) for i in idxs]).convex_hull
        exposures = [p.exposure for p in pairs]
        zones.append(Zone(
            polygon=hull.buffer(config.ZONE_BUFFER_M),
            height_min=min(exposures),
            height_max=max(exposures),
            n_anchors=len(idxs),
            n_pairs=len(pairs),
        ))
    return sorted(zones, key=lambda z: z.height_max, reverse=True)
