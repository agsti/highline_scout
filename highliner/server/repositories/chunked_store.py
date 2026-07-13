"""Viewport-windowed reads over the chunked region layout.

Layout under ``data/<region>/``:
    grid.json                    {"bbox": [...], "chunk_m": N, "crs": "..."}
    anchors/p_{cx}_{cy}.parquet  anchors per chunk
    pairs/q_{cx}_{cy}.parquet    candidate pairs per chunk

Each overlapping partition is read through the process-wide columnar cache
(``partition_cache``); the viewport window and the live slider thresholds are
applied as vectorized masks, so only the rows a request actually needs become
``Anchor``/``Candidate`` objects.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate, PairFilter
from highliner.server.repositories import partition_cache

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
    """Anchors from the partitions overlapping ``bbox``, clipped to ``bbox``.
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
            out.extend(partition_cache.anchor_columns(p).select(bbox))
    return out


def load_pairs_in_bbox(region_dir: Path, bbox: Bbox,
                       pair_filter: PairFilter | None = None) -> list[Candidate]:
    """Candidate pairs from the partitions overlapping ``bbox`` (expanded by
    MAX_PAIR_LEN so pairs straddling the viewport edge are included), keeping
    those whose segment intersects the viewport and, when ``pair_filter`` is
    given, pass the live slider thresholds. Raises HTTPException(413) if too many
    chunks overlap."""
    region_dir = Path(region_dir)
    grid = read_grid(region_dir)
    idx = chunk_indices_for_bbox(grid, _expand(bbox, config.MAX_PAIR_LEN))
    if len(idx) > config.MAX_VIEW_CHUNKS:
        raise HTTPException(413, "viewport too large; zoom in")
    out: list[Candidate] = []
    for cx, cy in idx:
        p = region_dir / "pairs" / f"q_{cx}_{cy}.parquet"
        if p.exists():
            out.extend(partition_cache.pair_columns(p).select(bbox, pair_filter))
    return out
