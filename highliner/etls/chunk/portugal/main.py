"""Portugal-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.portugal import dtm_dgt
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "portugal"
_CRS: Final[str] = "EPSG:3763"


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# DGT's 2024--25 coverage is mainland Portugal. Bounds are DGT's national
# extent transformed to PT-TM06/ETRS89 and rounded outward to 1 km.
REGIONS: tuple[Region, ...] = (
    Region("mainland", (-131000, -307000, 168000, 284000), _CRS,
           "dgt_mdt_2m", dtm_dgt.fetch),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-portugal")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at", help="skip regions before this id")
    parser.add_argument("--only", action="append", help="run only this region id")
    parser.add_argument("--jobs", type=int, default=1,
                        help="number of regions to precompute concurrently")
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    regions = REGIONS
    if args.start_at:
        if args.start_at != "mainland":
            raise SystemExit(f"unknown region for --start-at: {args.start_at}")
    if args.only:
        regions = tuple(region for region in regions if region.name in set(args.only))
    for region in regions:
        shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                          crs=region.crs, dtm_source=region.dtm_source,
                          fetch=region.fetch, workers=args.workers,
                          cache_dir=args.cache_dir)


if __name__ == "__main__":
    main()
