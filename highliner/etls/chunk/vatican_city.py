"""Vatican City configuration and CLI for chunk precompute.

The one region is a 2 km by 2 km, kilometre-rounded envelope around the
Vatican City State boundary.  It is deliberately larger than the microstate
so the fixed 10 km chunk grid has terrain context at its border.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "vatican_city"
_CRS: Final[str] = "EPSG:6875"


@dataclass(frozen=True)
class Region:
    """One Vatican City precompute target and its terrain source."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str


# Vatican City boundary (WGS84) transformed to EPSG:6875, then rounded out to
# kilometre coordinates. Source: Vatican City State boundary, OpenStreetMap.
REGIONS: tuple[Region, ...] = (
    Region("vatican_city", (7_036_000, 4_633_000, 7_038_000, 4_635_000),
           _CRS, "hrdtm"),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-vatican-city")
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
    """Format a duration as H:MM:SS."""
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
        dtm_source=region.dtm_source, workers=workers, cache_dir=cache_dir,
        report=report)
    print()
    print(f"[{region.name}] completed {count} chunks -> "
          f"{shared.region_output_dir(data_dir, COUNTRY, region.name)}", flush=True)
    return count


def main(argv: list[str] | None = None) -> None:
    """Precompute the Vatican City terrain-scanning envelope."""
    args = _parse_args(argv)
    if args.jobs != 1:
        raise SystemExit("--jobs must be 1: Vatican City has one region")
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    for region in _select_regions(args.start_at, args.only):
        _precompute_region(region, args.data_dir, args.cache_dir, args.workers)


if __name__ == "__main__":
    main()
