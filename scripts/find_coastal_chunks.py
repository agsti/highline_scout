"""Find (and optionally delete) already-computed chunks whose data predates
the ocean-adjacent cliff detection fix, so they can be reprocessed.

``process_chunk()`` is idempotent: a chunk whose pairs parquet already exists
is skipped, so simply re-running ``just etl-chunk`` after the ocean fix
landed does not pick up newly-detectable coastal cliffs in regions that were
already computed. This script finds exactly the chunks whose halo bbox
intersects the ocean polygon (the only ones the fix can actually change), and
can delete their anchors/pairs partitions -- plus the region's density files,
which aggregate across the whole region rather than per chunk -- so a
follow-up ``just etl-chunk``/``etl-density`` run recomputes only what
changed.

Usage:
    uv run python -m scripts.find_coastal_chunks chile          # dry run
    uv run python -m scripts.find_coastal_chunks chile --delete # actually delete
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from highliner.core import config
from highliner.etls.chunk import ocean
from highliner.etls.chunk.shared import Bbox, chunk_grid
from highliner.etls.density.shared import discover_regions
from highliner.server.repositories import chunked_store


def _halo_bbox(core: Bbox, halo: float) -> Bbox:
    minx, miny, maxx, maxy = core
    return (minx - halo, miny - halo, maxx + halo, maxy + halo)


def coastal_chunk_ids(bbox: Bbox, chunk_m: float, ocean_geom: BaseGeometry,
                      halo: float = config.CHUNK_HALO_M
                      ) -> list[tuple[int, int]]:
    """Return every ``(cx, cy)`` whose halo bbox -- the area ``process_chunk``
    actually fetches terrain for -- intersects ``ocean_geom``."""
    return [(cx, cy) for cx, cy, core in chunk_grid(bbox, chunk_m)
            if box(*_halo_bbox(core, halo)).intersects(ocean_geom)]


@dataclass(frozen=True)
class RegionPlan:
    region_dir: Path
    total_chunks: int
    coastal_chunk_ids: list[tuple[int, int]]
    chunk_files: list[Path]
    density_dir: Path | None


def plan_region(region_dir: Path, ocean_geom: BaseGeometry,
                halo: float = config.CHUNK_HALO_M) -> RegionPlan:
    """Determine which of one region's chunks are coastal, and which
    already-computed files a reprocessing pass would need removed first.

    Density files aren't per chunk -- they aggregate every pair in the
    region -- so if any chunk is coastal, the whole density/ directory is
    included rather than trying to patch individual zoom files."""
    grid = chunked_store.read_grid(region_dir)
    total = sum(1 for _ in chunk_grid(grid.bbox, grid.chunk_m))
    coastal = coastal_chunk_ids(grid.bbox, grid.chunk_m, ocean_geom, halo)

    chunk_files: list[Path] = []
    for cx, cy in coastal:
        for path in (region_dir / "anchors" / f"p_{cx}_{cy}.parquet",
                     region_dir / "pairs" / f"q_{cx}_{cy}.parquet"):
            if path.exists():
                chunk_files.append(path)

    all_density = region_dir / "density"
    density_dir = all_density if coastal and all_density.is_dir() else None

    return RegionPlan(region_dir, total, coastal, chunk_files, density_dir)


def _delete(plan: RegionPlan) -> int:
    """Delete a plan's files. Returns the count removed."""
    removed = 0
    for path in plan.chunk_files:
        path.unlink()
        removed += 1
    if plan.density_dir is not None:
        for path in plan.density_dir.glob("*.npz"):
            path.unlink()
            removed += 1
    return removed


def _report(country: str, plans: list[RegionPlan], deleted: bool) -> None:
    any_coastal = False
    for plan in plans:
        name = plan.region_dir.name
        if not plan.coastal_chunk_ids:
            print(f"[{name}] 0/{plan.total_chunks} chunks coastal")
            continue
        any_coastal = True
        action = "deleted" if deleted else "would delete"
        density_note = " + density/" if plan.density_dir is not None else ""
        print(f"[{name}] {len(plan.coastal_chunk_ids)}/{plan.total_chunks} "
              f"chunks coastal, {action} {len(plan.chunk_files)} chunk "
              f"file(s){density_note}")

    if not any_coastal:
        print(f"{country}: no coastal chunks found, nothing to do")
        return

    print()
    if deleted:
        print("Now run:")
    else:
        print("Re-run with --delete to remove these files, then run:")
    print(f"  just etl-chunk {country} <concurrency>")
    print(f"  just etl-density {country}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="find-coastal-chunks")
    parser.add_argument("country")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--delete", action="store_true",
                        help="delete matching chunk/density files "
                             "(default: dry run, list only)")
    args = parser.parse_args(argv)

    regions = discover_regions(args.data_dir, args.country)
    if not regions:
        print(f"no regions found for {args.country} under {args.data_dir}")
        return 1

    plans = []
    for region_dir in regions:
        crs = chunked_store.read_grid(region_dir).crs
        ocean_geom = ocean.load_ocean_geometry(crs)
        plans.append(plan_region(region_dir, ocean_geom))

    if args.delete:
        for plan in plans:
            _delete(plan)

    _report(args.country, plans, deleted=args.delete)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
