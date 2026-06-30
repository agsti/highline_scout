"""Batch precompute of anchors + candidate pairs for all of Catalonia.

Tiles the region into ``chunk_m`` squares processed independently: download DTM
tiles (+halo), extract anchors, find candidate pairs at a loose envelope, keep
core anchors and canonically-owned pairs, write parquet partitions, then delete
the raw downloads. RAM is bounded to one chunk; no DTM persists.
"""
import json
import math
from pathlib import Path
from typing import Callable, Iterator

from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.repositories import dtm
from highliner.repositories.anchors import save_anchors
from highliner.repositories.candidates import save_candidates
from highliner.services.pairing import find_candidates
from highliner.services.terrain import extract_anchors

Bbox = tuple[float, float, float, float]


def chunk_grid(bbox: Bbox, chunk_m: float) -> Iterator[tuple[int, int, Bbox]]:
    """Yield ``(cx, cy, core_bbox)`` tiling ``bbox`` into ``chunk_m`` squares.
    Edge chunk cores are clipped to the bbox max edge."""
    minx, miny, maxx, maxy = bbox
    nx = math.ceil((maxx - minx) / chunk_m)
    ny = math.ceil((maxy - miny) / chunk_m)
    for cy in range(ny):
        for cx in range(nx):
            x0 = minx + cx * chunk_m
            y0 = miny + cy * chunk_m
            yield cx, cy, (x0, y0, min(x0 + chunk_m, maxx), min(y0 + chunk_m, maxy))
