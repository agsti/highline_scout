"""Batch precompute of anchors + candidate pairs for one region.

Tiles the region into ``chunk_m`` squares processed independently: download DTM
tiles (+halo), extract anchors, find candidate pairs at a loose envelope, keep
core anchors and canonically-owned pairs, write parquet partitions, then delete
the raw downloads. RAM is bounded to one chunk; no DTM persists.
"""
import concurrent.futures
import json
import math
import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

from highliner.core import config
from highliner.core.regions import country_for_region, defaults_for_region, region_dir
from highliner.etl.chunk.anchors import save_anchors
from highliner.etl.chunk.candidates import save_candidates
from highliner.etl.repositories import dtm
from highliner.etl.services.pairing import find_candidates
from highliner.etl.services.terrain import extract_anchors
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate

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


def _cleanup_transient_tiles(tiles: list[Path], tiles_dir: Path) -> None:
    for t in tiles:
        if t.parent == tiles_dir:
            t.unlink(missing_ok=True)
    shutil.rmtree(tiles_dir, ignore_errors=True)


def process_chunk(cx: int, cy: int, core_bbox: Bbox, region_dir: Path,  # noqa: PLR0913
                  halo: float = config.CHUNK_HALO_M,
                  crs: str = config.UTM_CRS,
                  dtm_source: str = "icgc",
                  cnig_cache_dir: Path | None = None) -> int:
    """Process one chunk into anchor + pair partitions. Returns the number of
    pairs kept. Idempotent: a chunk whose pair partition exists is skipped
    (returns -1)."""
    qpath = region_dir / "pairs" / f"q_{cx}_{cy}.parquet"
    if qpath.exists():
        return -1

    minx, miny, maxx, maxy = core_bbox
    halo_bbox = (minx - halo, miny - halo, maxx + halo, maxy + halo)
    tiles_dir = region_dir / "tiles" / f"chunk_{cx}_{cy}_{os.getpid()}"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    try:
        tiles = dtm.fetch_tiles(halo_bbox, tiles_dir,
                                source=dtm_source, crs=crs,
                                cnig_cache_dir=cnig_cache_dir)
    except Exception:
        # Failed download (e.g. exhausted rate-limit retries): drop the
        # partial tiles and re-raise so the chunk stays unfinished/retriable.
        _cleanup_transient_tiles([], tiles_dir)
        raise

    try:
        core_anchors: list[Anchor] = []
        owned_pairs: list[Candidate] = []
        raster = dtm.raster_from_tiles(tiles, bbox=halo_bbox)
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
                # Own a cross-chunk pair via its canonical endpoint. Round the
                # tie-break coords so sub-meter drift between a pair re-extracted in
                # adjacent chunks can't flip which endpoint is "canonical" (which
                # could drop or duplicate a seam-crossing line).
                kx, ky = min(
                    (float(round(c.a.x)), float(round(c.a.y)), c.a.x, c.a.y),
                    (float(round(c.b.x)), float(round(c.b.y)), c.b.x, c.b.y))[2:]
                if _in_core(kx, ky, core_bbox):
                    owned_pairs.append(c)

        (region_dir / "anchors").mkdir(parents=True, exist_ok=True)
        (region_dir / "pairs").mkdir(parents=True, exist_ok=True)
        apath = region_dir / "anchors" / f"p_{cx}_{cy}.parquet"
        tmp_id = f"tmp-{os.getpid()}-{cx}-{cy}"
        atmp = apath.with_name(f"{apath.name}.{tmp_id}")
        qtmp = qpath.with_name(f"{qpath.name}.{tmp_id}")
        try:
            save_anchors(core_anchors, atmp)
            save_candidates(owned_pairs, qtmp)
            atmp.replace(apath)
            qtmp.replace(qpath)
        except Exception:
            atmp.unlink(missing_ok=True)
            qtmp.unlink(missing_ok=True)
            raise
    finally:
        _cleanup_transient_tiles(tiles, tiles_dir)
    return len(owned_pairs)


def precompute(  # noqa: PLR0913
        region: str, bbox: Bbox, data_dir: Path,
        chunk_m: float = config.CHUNK_M,
        report: Callable[[int, int], None] | None = None,
        crs: str | None = None,
        dtm_source: str | None = None,
        workers: int = 1,
        cache_dir: Path | None = None) -> int:
    """Precompute anchors + pairs for ``bbox`` under
    ``data_dir/<country>/<region>``. Writes grid.json, then processes every
    chunk (skipping finished ones). Returns the number of chunks. The CNIG
    source cache is kept per-country under ``cache_dir`` (default
    ``config.CACHE_DIR``), outside ``data_dir``."""
    if workers < 1:
        raise ValueError("workers must be >= 1")

    rdir = region_dir(data_dir, region)
    cnig_cache_dir = Path(cache_dir or config.CACHE_DIR) / country_for_region(region)
    defaults = defaults_for_region(region)
    crs = crs or defaults.crs
    dtm_source = dtm_source or defaults.dtm_source
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "grid.json").write_text(json.dumps(
        {"bbox": list(bbox), "chunk_m": chunk_m,
         "crs": crs, "dtm_source": dtm_source}))

    chunks = list(chunk_grid(bbox, chunk_m))
    total = len(chunks)
    if workers == 1:
        for i, (cx, cy, core) in enumerate(chunks, start=1):
            process_chunk(cx, cy, core, rdir, crs=crs, dtm_source=dtm_source,
                          cnig_cache_dir=cnig_cache_dir)
            if report is not None:
                report(i, total)
        return total

    done = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(process_chunk, cx, cy, core, rdir,
                        crs=crs, dtm_source=dtm_source,
                        cnig_cache_dir=cnig_cache_dir)
            for cx, cy, core in chunks
        ]
        for future in concurrent.futures.as_completed(futures):
            future.result()
            done += 1
            if report is not None:
                report(done, total)
    return total
