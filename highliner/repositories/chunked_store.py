"""Viewport-windowed reads over the chunked region layout.

Layout under ``data/<region>/``:
    grid.json                    {"bbox": [...], "chunk_m": N, "crs": "..."}
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
    crs: str
    dtm_source: str


def read_grid(region_dir: Path) -> Grid:
    data = json.loads((Path(region_dir) / "grid.json").read_text())
    b = [float(v) for v in data["bbox"]]
    return Grid(
        bbox=(b[0], b[1], b[2], b[3]),
        chunk_m=float(data["chunk_m"]),
        crs=str(data.get("crs", config.UTM_CRS)),
        dtm_source=str(data.get("dtm_source", "icgc")),
    )


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


def _expand(bbox: Bbox, m: float) -> Bbox:
    return (bbox[0] - m, bbox[1] - m, bbox[2] + m, bbox[3] + m)


def load_anchors_in_bbox(region_dir: Path, bbox: Bbox) -> list[Anchor]:
    """Anchors from the partitions overlapping ``bbox``.
    Raises HTTPException(413) if too many chunks overlap."""
    region_dir = Path(region_dir)
    grid = read_grid(region_dir)
    idx = chunk_indices_for_bbox(grid, bbox)
    if len(idx) > config.MAX_VIEW_CHUNKS:
        raise HTTPException(413, "viewport too large; zoom in")
    out: list[Anchor] = []
    for cx, cy in idx:
        p = region_dir / "anchors" / f"p_{cx}_{cy}.parquet"
        if p.exists():
            out.extend(load_anchors(p))
    return out


def _segment_intersects(c: Candidate, bbox: Bbox) -> bool:
    minx, miny, maxx, maxy = bbox
    return (min(c.a.x, c.b.x) <= maxx and max(c.a.x, c.b.x) >= minx
            and min(c.a.y, c.b.y) <= maxy and max(c.a.y, c.b.y) >= miny)


def load_pairs_in_bbox(region_dir: Path, bbox: Bbox) -> list[Candidate]:
    """Candidate pairs from the partitions overlapping ``bbox`` (expanded by
    MAX_PAIR_LEN so pairs straddling the viewport edge are included), filtered to
    those whose segment intersects the viewport. Raises HTTPException(413) if too
    many chunks overlap."""
    region_dir = Path(region_dir)
    grid = read_grid(region_dir)
    idx = chunk_indices_for_bbox(grid, _expand(bbox, config.MAX_PAIR_LEN))
    if len(idx) > config.MAX_VIEW_CHUNKS:
        raise HTTPException(413, "viewport too large; zoom in")
    out: list[Candidate] = []
    for cx, cy in idx:
        p = region_dir / "pairs" / f"q_{cx}_{cy}.parquet"
        if p.exists():
            out.extend(c for c in load_candidates(p) if _segment_intersects(c, bbox))
    return out
