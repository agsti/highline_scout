"""Luxembourg-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.luxembourg import dtm_act
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "luxembourg"
_CRS: Final[str] = "EPSG:2169"
__all__ = ["main", "shared"]


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# National administrative boundary (ACT), reprojected to LUREF and rounded
# outward to 1 km. The ACT DTM contains no elevations outside this territory.
REGIONS = (Region("luxembourg", (48_000, 56_000, 107_000, 139_000), _CRS,
                  "act_lidar_2019_mnt", dtm_act.fetch),)


def _fmt_hms(seconds: float) -> str:
    value = int(seconds)
    return f"{value // 3600}:{value % 3600 // 60:02d}:{value % 60:02d}"


def _select_regions(start_at: str | None, only: list[str] | None) -> tuple[Region, ...]:
    if start_at and start_at != "luxembourg":
        raise SystemExit(f"unknown region for --start-at: {start_at}")
    return () if only and "luxembourg" not in set(only) else REGIONS


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-luxembourg")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at")
    parser.add_argument("--only", action="append")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    for region in _select_regions(args.start_at, args.only):
        start = time.monotonic()

        def report(done: int, total: int, started: float = start) -> None:
            elapsed = time.monotonic() - started
            pct = 100 * done / total if total else 100
            eta = elapsed / done * (total - done) if done else 0
            print(f"\rchunk {done}/{total} ({pct:4.1f}%)  elapsed {_fmt_hms(elapsed)}  "
                  f"eta {_fmt_hms(eta)}", end="", flush=True)

        print(f"[{region.name}] starting precompute", flush=True)
        count = shared.precompute(
            COUNTRY, region.name, region.bbox, args.data_dir, crs=region.crs,
            dtm_source=region.dtm_source, fetch=region.fetch,
            workers=args.workers, cache_dir=args.cache_dir, report=report)
        print()
        print(f"[{region.name}] completed {count} chunks -> "
              f"{shared.region_output_dir(args.data_dir, COUNTRY, region.name)}")
