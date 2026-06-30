"""Viewport-windowed reads over the chunked ``catalonia`` layout.

Layout under ``data/catalonia/``:
    grid.json                    {"bbox": [minx,miny,maxx,maxy], "chunk_m": N}
    anchors/p_{cx}_{cy}.parquet  anchors per chunk
    pairs/q_{cx}_{cy}.parquet    candidate pairs per chunk
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.repositories.anchors import load_anchors
from highliner.repositories.candidates import load_candidates

Bbox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Grid:
    bbox: Bbox
    chunk_m: float


def read_grid(region_dir: Path) -> Grid:
    data = json.loads((Path(region_dir) / "grid.json").read_text())
    b = [float(v) for v in data["bbox"]]
    return Grid(bbox=(b[0], b[1], b[2], b[3]), chunk_m=float(data["chunk_m"]))


def chunk_indices_for_bbox(grid: Grid, bbox: Bbox) -> list[tuple[int, int]]:
    """Indices of chunks whose core overlaps ``bbox``, clipped to the grid."""
    minx, miny, maxx, maxy = grid.bbox
    nx = math.ceil((maxx - minx) / grid.chunk_m)
    ny = math.ceil((maxy - miny) / grid.chunk_m)
    bx0, by0, bx1, by1 = bbox
    cx0 = max(0, int(math.floor((bx0 - minx) / grid.chunk_m)))
    cx1 = min(nx - 1, int(math.floor((bx1 - minx) / grid.chunk_m)))
    cy0 = max(0, int(math.floor((by0 - miny) / grid.chunk_m)))
    cy1 = min(ny - 1, int(math.floor((by1 - miny) / grid.chunk_m)))
    return [(cx, cy) for cy in range(cy0, cy1 + 1) for cx in range(cx0, cx1 + 1)]
