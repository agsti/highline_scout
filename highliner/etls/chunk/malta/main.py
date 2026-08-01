"""Malta-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.malta import dtm_pa
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "malta"
_CRS: Final[str] = "EPSG:32633"
__all__ = ["main", "shared"]


@dataclass(frozen=True)
class Region:
    """One Malta precompute target and its terrain source configuration."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


REGIONS: tuple[Region, ...] = (
    Region("malta", (425_000, 3_959_000, 462_000, 3_994_000), _CRS,
           "pa_dtm_2018_wcs", dtm_pa.fetch),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-malta")
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
    return tuple(region for region in regions if not only or region.name in set(only))


def _precompute_region(region: Region, data_dir: Path, cache_dir: Path,
                       workers: int) -> int:
    print(f"[{region.name}] starting precompute", flush=True)
    started = time.monotonic()

    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - started
        print(f"\rchunk {done}/{total} elapsed {elapsed:.0f}s", end="", flush=True)

    count = shared.precompute(
        COUNTRY, region.name, region.bbox, data_dir, crs=region.crs,
        dtm_source=region.dtm_source, fetch=region.fetch, workers=workers,
        cache_dir=cache_dir, report=report)
    print()
    return count


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    for region in _select_regions(args.start_at, args.only):
        _precompute_region(region, args.data_dir, args.cache_dir, args.workers)
