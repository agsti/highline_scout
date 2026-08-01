"""Cyprus-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.cyprus import dtm_dls
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "cyprus"
_CRS: Final[str] = "EPSG:32636"
__all__ = ["main", "shared"]


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# Republic of Cyprus DLS protected-sites extent, transformed to UTM 36N and
# rounded outward to one kilometre. The DLS DTM itself determines coverage.
REGIONS: tuple[Region, ...] = (
    Region("cyprus", (431000, 3822000, 649000, 3955000), _CRS,
           "dls_dtm_2019", dtm_dls.fetch),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-cyprus")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at", help="skip regions before this id")
    parser.add_argument("--only", action="append", help="run only this region id")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args(argv)


def _select_regions(start_at: str | None, only: list[str] | None) -> tuple[Region, ...]:
    if start_at and start_at != COUNTRY:
        raise SystemExit(f"unknown region for --start-at: {start_at}")
    return () if only and COUNTRY not in set(only) else REGIONS


def _fmt_hms(seconds: float) -> str:
    seconds_int = int(seconds)
    return (f"{seconds_int // 3600}:{(seconds_int % 3600) // 60:02d}:"
            f"{seconds_int % 60:02d}")


def _precompute(region: Region, data_dir: Path, cache_dir: Path, workers: int) -> None:
    print(f"[{region.name}] starting precompute", flush=True)
    start = time.monotonic()

    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - start
        pct = 100.0 * done / total if total else 100.0
        eta = elapsed / done * (total - done) if done else 0.0
        print(f"\rchunk {done}/{total} ({pct:4.1f}%) elapsed {_fmt_hms(elapsed)} "
              f"eta {_fmt_hms(eta)}", end="", flush=True)

    count = shared.precompute(
        COUNTRY, region.name, region.bbox, data_dir, crs=region.crs,
        dtm_source=region.dtm_source, fetch=region.fetch, workers=workers,
        cache_dir=cache_dir, report=report)
    print()
    print(f"[{region.name}] completed {count} chunks -> "
          f"{shared.region_output_dir(data_dir, COUNTRY, region.name)}", flush=True)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    for region in _select_regions(args.start_at, args.only):
        _precompute(region, args.data_dir, args.cache_dir, args.workers)
