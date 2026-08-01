"""Slovenia-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.shared import Bbox
from highliner.etls.chunk.slovenia import dtm_arso

COUNTRY: Final[str] = "slovenia"
__all__ = ["main", "shared"]
_CRS: Final[str] = "EPSG:3794"


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# GURS administrative-boundary extent in D96/TM, rounded outward to 1 km.
REGIONS = (Region("slovenia", (374000, 30000, 625000, 196000), _CRS,
                  "arso_dmr1", dtm_arso.fetch),)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-slovenia")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at")
    parser.add_argument("--only", action="append")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args(argv)


def _select_regions(start_at: str | None, only: list[str] | None) -> tuple[Region, ...]:
    if start_at and start_at != COUNTRY:
        raise SystemExit(f"unknown region for --start-at: {start_at}")
    return () if only and COUNTRY not in set(only) else REGIONS


def _fmt_hms(seconds: float) -> str:
    seconds_int = int(seconds)
    return (f"{seconds_int // 3600}:{seconds_int % 3600 // 60:02d}:"
            f"{seconds_int % 60:02d}")


def _precompute(region: Region, data_dir: Path, cache_dir: Path, workers: int) -> None:
    print(f"[{region.name}] starting precompute", flush=True)
    start = time.monotonic()
    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - start
        eta = elapsed / done * (total - done) if done else 0.0
        print(f"\rchunk {done}/{total} elapsed {_fmt_hms(elapsed)} eta {_fmt_hms(eta)}",
              end="", flush=True)
    count = shared.precompute(COUNTRY, region.name, region.bbox, data_dir,
                              crs=region.crs, dtm_source=region.dtm_source,
                              fetch=region.fetch, workers=workers,
                              cache_dir=cache_dir, report=report)
    print(f"\n[{region.name}] completed {count} chunks", flush=True)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    for region in _select_regions(args.start_at, args.only):
        _precompute(region, args.data_dir, args.cache_dir, args.workers)
