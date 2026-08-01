"""Indonesia-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import concurrent.futures
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.indonesia import dtm_demnas
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "indonesia"


@dataclass(frozen=True)
class Region:
    """One Indonesian precompute target and terrain source configuration."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


def _region(name: str, bbox: Bbox, crs: str) -> Region:
    return Region(name, bbox, crs, "demnas", dtm_demnas.fetch)


# BIG's administrative boundary service was reprojected into the predominant
# UTM zone of each large island group and rounded outward to 1 km.  Splitting
# the archipelago keeps local distance/slope calculations within a practical
# projection distortion range.
REGIONS: tuple[Region, ...] = (
    _region("sumatra", (120000, 9450000, 900000, 10560000), "EPSG:32747"),
    _region("java", (130000, 9044000, 860000, 9318000), "EPSG:32749"),
    _region("kalimantan", (170000, 9554000, 890000, 10456000), "EPSG:32750"),
    _region("lesser_sunda", (150000, 8880000, 930000, 9156000), "EPSG:32750"),
    _region("sulawesi", (150000, 9507000, 890000, 10103000), "EPSG:32751"),
    _region("maluku", (180000, 9620000, 900000, 10150000), "EPSG:32752"),
    _region("papua", (150000, 9359000, 900000, 10055000), "EPSG:32753"),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-indonesia")
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
        print(f"\rchunk {done}/{total} ({pct:4.1f}%)  "
              f"elapsed {_fmt_hms(elapsed)}  eta {_fmt_hms(eta)}",
              end="", flush=True)

    count = shared.precompute(
        COUNTRY, region.name, region.bbox, data_dir, crs=region.crs,
        dtm_source=region.dtm_source, fetch=region.fetch, workers=workers,
        cache_dir=cache_dir, report=report)
    print()
    print(f"[{region.name}] completed {count} chunks -> "
          f"{shared.region_output_dir(data_dir, COUNTRY, region.name)}", flush=True)
    return count


def _run_parallel(regions: tuple[Region, ...], data_dir: Path, cache_dir: Path,
                  jobs: int, workers: int) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(_precompute_region, region, data_dir, cache_dir,
                        workers): region
            for region in regions
        }
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
    if args.jobs < 1:
        raise SystemExit("--jobs must be >= 1")
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    regions = _select_regions(args.start_at, args.only)
    if args.jobs == 1:
        for region in regions:
            _precompute_region(region, args.data_dir, args.cache_dir, args.workers)
        return
    _run_parallel(regions, args.data_dir, args.cache_dir, args.jobs, args.workers)
