"""Japan-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.japan import dtm_gsi
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "japan"


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# GSI national land coverage, split by UTM zone and rounded out to 1 km.
REGIONS: tuple[Region, ...] = (
    Region("japan_west", (180000, 3300000, 780000, 4050000), "EPSG:32652",
           "gsi_dem", dtm_gsi.fetch),
    Region("japan_central", (170000, 3300000, 820000, 4250000), "EPSG:32653",
           "gsi_dem", dtm_gsi.fetch),
    Region("japan_east", (170000, 3400000, 820000, 4550000), "EPSG:32654",
           "gsi_dem", dtm_gsi.fetch),
    Region("japan_hokkaido", (200000, 4600000, 720000, 5050000), "EPSG:32655",
           "gsi_dem", dtm_gsi.fetch),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-japan")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at")
    parser.add_argument("--only", action="append")
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


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    for region in _select_regions(args.start_at, args.only):
        start = time.monotonic()
        count = shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                                  crs=region.crs, dtm_source=region.dtm_source,
                                  fetch=region.fetch, workers=args.workers,
                                  cache_dir=args.cache_dir)
        elapsed = time.monotonic() - start
        print(f"[{region.name}] completed {count} chunks in {elapsed:.0f}s")
