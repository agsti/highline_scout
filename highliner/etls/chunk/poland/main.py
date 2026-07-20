"""Poland-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.poland import dtm_wcs
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "poland"
_CRS: Final[str] = "EPSG:2180"


@dataclass(frozen=True)
class Region:
    """One Poland precompute target and its terrain source configuration."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# GUGiK GRID1 coverage bounds, rounded outward to the chunk grid.  This is the
# complete national service extent, including its nodata margin at borders.
REGIONS: tuple[Region, ...] = (
    Region("poland", (90_000, 160_000, 800_000, 880_000), _CRS, "poland_wcs",
           dtm_wcs.fetch),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-poland")
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
        dtm_source=region.dtm_source, fetch=region.fetch,
        workers=workers, cache_dir=cache_dir,
        report=report)
    print()
    print(f"[{region.name}] completed {count} chunks -> "
          f"{shared.region_output_dir(data_dir, COUNTRY, region.name)}", flush=True)
    return count


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1:
        raise SystemExit("--jobs must be >= 1")
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    regions = _select_regions(args.start_at, args.only)
    for region in regions:
        _precompute_region(region, args.data_dir, args.cache_dir, args.workers)


if __name__ == "__main__":
    main()
