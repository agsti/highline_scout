"""Austria-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import concurrent.futures
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "austria"
_CRS: Final[str] = "EPSG:3035"


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str


def _region(name: str, bbox: Bbox) -> Region:
    return Region(name, bbox, _CRS, "bev_als_dtm")


# Austrian federal-state bounds from Statistik Austria's administrative-boundary
# service, reprojected to the source's native ETRS89/LAEA CRS and rounded
# outward to kilometres.  Bboxes intentionally include border terrain so a
# cross-border gap can be detected from either side.
REGIONS: tuple[Region, ...] = (
    _region("vorarlberg", (4282000, 2631000, 4352000, 2721000)),
    _region("tyrol", (4321000, 2620000, 4543000, 2725000)),
    _region("carinthia", (4518000, 2579000, 4722000, 2691000)),
    _region("upper_austria", (4519000, 2702000, 4714000, 2868000)),
    _region("salzburg", (4522000, 2635000, 4619000, 2762000)),
    _region("styria", (4582000, 2615000, 4804000, 2775000)),
    _region("lower_austria", (4642000, 2708000, 4864000, 2914000)),
    _region("burgenland", (4767000, 2650000, 4871000, 2803000)),
    _region("vienna", (4772000, 2795000, 4813000, 2826000)),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-austria")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at", help="skip regions before this id")
    parser.add_argument("--only", action="append", help="run only this region id")
    parser.add_argument("--jobs", type=int, default=1,
                        help="number of regions to precompute concurrently")
    parser.add_argument("--workers", type=int, default=1,
                        help="number of chunks to precompute concurrently per region")
    return parser.parse_args(argv)


def _select_regions(start_at: str | None, only: list[str] | None) -> tuple[Region, ...]:
    regions = REGIONS
    if start_at:
        names = [region.name for region in regions]
        if start_at not in names:
            raise SystemExit(f"unknown region for --start-at: {start_at}")
        regions = regions[names.index(start_at):]
    if only:
        wanted = set(only)
        regions = tuple(region for region in regions if region.name in wanted)
    return regions


def _fmt_hms(seconds: float) -> str:
    seconds_int = int(seconds)
    return (f"{seconds_int // 3600}:"
            f"{(seconds_int % 3600) // 60:02d}:{seconds_int % 60:02d}")


def _precompute_region(region: Region, data_dir: Path, cache_dir: Path,
                       workers: int) -> int:
    print(f"[{region.name}] starting precompute", flush=True)
    start = time.monotonic()

    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - start
        pct = 100.0 * done / total if total else 100.0
        eta = elapsed / done * (total - done) if done else 0.0
        print(f"\rchunk {done}/{total} ({pct:4.1f}%)  elapsed {_fmt_hms(elapsed)}  "
              f"eta {_fmt_hms(eta)}", end="", flush=True)

    count = shared.precompute(
        COUNTRY, region.name, region.bbox, data_dir, crs=region.crs,
        dtm_source=region.dtm_source, workers=workers, cache_dir=cache_dir,
        report=report)
    print()
    print(f"[{region.name}] completed {count} chunks -> "
          f"{shared.region_output_dir(data_dir, COUNTRY, region.name)}", flush=True)
    return count


def _run_parallel(regions: tuple[Region, ...], data_dir: Path, cache_dir: Path,
                  jobs: int, workers: int) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(_precompute_region, region, data_dir, cache_dir,
                               workers):
                   region for region in regions}
        for future in concurrent.futures.as_completed(futures):
            region = futures[future]
            try:
                future.result()
            except Exception as exc:
                for pending in futures:
                    pending.cancel()
                raise RuntimeError(f"{region.name} failed") from exc


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    regions = _select_regions(args.start_at, args.only)
    if args.jobs == 1:
        for region in regions:
            _precompute_region(region, args.data_dir, args.cache_dir, args.workers)
        return
    _run_parallel(regions, args.data_dir, args.cache_dir, args.jobs, args.workers)


if __name__ == "__main__":
    main()
