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


def _in_core(x: float, y: float, core: Bbox) -> bool:
    return core[0] <= x < core[2] and core[1] <= y < core[3]


def process_chunk(cx: int, cy: int, core_bbox: Bbox, region_dir: Path,
                  halo: float = config.CHUNK_HALO_M) -> int:
    """Process one chunk into anchor + pair partitions. Returns the number of
    pairs kept. Idempotent: a chunk whose pair partition exists is skipped
    (returns -1)."""
    qpath = region_dir / "pairs" / f"q_{cx}_{cy}.parquet"
    if qpath.exists():
        return -1

    minx, miny, maxx, maxy = core_bbox
    halo_bbox = (minx - halo, miny - halo, maxx + halo, maxy + halo)
    tiles = dtm.fetch_tiles(halo_bbox, region_dir / "tiles")

    core_anchors: list[Anchor] = []
    owned_pairs: list[Candidate] = []
    raster = dtm.raster_from_tiles(tiles)
    if raster is not None:
        anchors = extract_anchors(
            raster, slope_min=config.SLOPE_MIN_DEG, radius=config.DROP_RADIUS_M,
            n_azimuths=config.N_AZIMUTHS, min_sector_drop=config.MIN_SECTOR_DROP_M,
            thin_dist=config.THIN_DIST_M)
        core_anchors = [a for a in anchors if _in_core(a.x, a.y, core_bbox)]
        cands = find_candidates(
            anchors, raster, max_len=config.MAX_PAIR_LEN,
            min_len=config.PRECOMPUTE_MIN_LEN_M,
            min_exposure=config.PRECOMPUTE_MIN_EXPOSURE_M,
            max_dh=config.PRECOMPUTE_MAX_DH_M)
        for c in cands:
            kx, ky = min((c.a.x, c.a.y), (c.b.x, c.b.y))
            if _in_core(kx, ky, core_bbox):
                owned_pairs.append(c)

    (region_dir / "anchors").mkdir(parents=True, exist_ok=True)
    (region_dir / "pairs").mkdir(parents=True, exist_ok=True)
    save_anchors(core_anchors, region_dir / "anchors" / f"p_{cx}_{cy}.parquet")
    save_candidates(owned_pairs, qpath)
    for t in tiles:
        t.unlink(missing_ok=True)
    return len(owned_pairs)
