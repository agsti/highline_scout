"""Sweden-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.shared import Bbox
from highliner.etls.chunk.sweden import dtm_lantmateriet

COUNTRY: Final[str] = "sweden"
_CRS: Final[str] = "EPSG:3006"


@dataclass(frozen=True)
class Region:
    """One Sweden precompute target and its terrain source configuration."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# Sweden's national envelope in SWEREF 99 TM, rounded outward to 1 km.
REGIONS: tuple[Region, ...] = (
    Region("sweden", (260_000, 6_120_000, 940_000, 7_690_000), _CRS,
           "lantmateriet_markhojdmodell", dtm_lantmateriet.fetch),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-sweden")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at", help="skip regions before this id")
    parser.add_argument("--only", action="append", help="run only this region id")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args(argv)


def _select_regions(start_at: str | None, only: list[str] | None) -> tuple[Region, ...]:
    regions = REGIONS
    if start_at:
        names = [region.name for region in regions]
        if start_at not in names:
            raise SystemExit(f"unknown region for --start-at: {start_at}")
        regions = regions[names.index(start_at):]
    if only:
        regions = tuple(region for region in regions if region.name in set(only))
    return regions


def _precompute_region(region: Region, data_dir: Path, cache_dir: Path,
                       workers: int) -> int:
    start = time.monotonic()
    count = shared.precompute(COUNTRY, region.name, region.bbox, data_dir,
                              crs=region.crs, dtm_source=region.dtm_source,
                              fetch=region.fetch, workers=workers,
                              cache_dir=cache_dir)
    print(f"[{region.name}] completed {count} chunks in "
          f"{int(time.monotonic() - start)}s", flush=True)
    return count


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    for region in _select_regions(args.start_at, args.only):
        _precompute_region(region, args.data_dir, args.cache_dir, args.workers)
