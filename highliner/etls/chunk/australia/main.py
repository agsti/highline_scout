"""Australia-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.australia import dtm_ga
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "australia"
CRS: Final[str] = "EPSG:3577"


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


def _region(name: str, bbox: Bbox) -> Region:
    return Region(name, bbox, CRS, "ga_lidar_5m", dtm_ga.fetch)


# State/territory administrative extents, transformed to GDA2020 Australian
# Albers and rounded outward to 1 km. Offshore external territories are excluded.
REGIONS = (
    _region("australian_capital_territory", (1502000, -4035000, 1578000, -3932000)),
    _region("new_south_wales", (789000, -4274000, 2097000, -3080000)),
    _region("northern_territory", (-337000, -2841000, 684000, -1138000)),
    _region("queensland", (575000, -3362000, 2452000, -967000)),
    _region("south_australia", (-297000, -4195000, 901000, -2806000)),
    _region("tasmania", (975000, -4876000, 1443000, -4366000)),
    _region("victoria", (776000, -4410000, 1660000, -3728000)),
    _region("western_australia", (-2099000, -3976000, -272000, -1442000)),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-australia")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--only", action="append")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args(argv)


def _precompute(region: Region, args: argparse.Namespace) -> int:
    return shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                             crs=region.crs, dtm_source=region.dtm_source,
                             fetch=region.fetch, workers=args.workers,
                             cache_dir=args.cache_dir)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    regions = tuple(region for region in REGIONS
                    if not args.only or region.name in args.only)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(lambda region: _precompute(region, args), regions))
