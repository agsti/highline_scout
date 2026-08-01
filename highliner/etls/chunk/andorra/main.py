"""Andorra-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.andorra import dtm_govern
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "andorra"
_CRS: Final[str] = "EPSG:27563"
__all__ = ["main", "shared"]


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


REGIONS = (Region("andorra", (523_000, 14_000, 556_000, 41_000), _CRS,
                  "govern_andorra_lidar_2025", dtm_govern.fetch),)


def main(argv: list[str] | None = None) -> None:
    """Precompute Andorra's one national region."""
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-andorra")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--only", action="append", help="run only this region id")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    regions = tuple(region for region in REGIONS if not args.only
                    or region.name in set(args.only))
    for region in regions:
        shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                          crs=region.crs, dtm_source=region.dtm_source,
                          fetch=region.fetch, workers=args.workers,
                          cache_dir=args.cache_dir)
