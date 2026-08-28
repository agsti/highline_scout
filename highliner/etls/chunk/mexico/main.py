"""Mexico CLI adapter for INEGI 5 m terrain precompute."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.mexico import dtm_inegi
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "mexico"
_CRS: Final[str] = "EPSG:6372"
__all__ = ["main", "shared"]


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# INEGI national boundary, reprojected to Mexico ITRF2008 / LCC and rounded
# outward to kilometres. The sheet catalogue drops offshore/foreign chunks.
REGIONS: tuple[Region, ...] = (
    Region("central", (706000, 314000, 4185000, 2394000), _CRS,
           "inegi_mdt5", dtm_inegi.fetch),
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-mexico")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--only", action="append")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    for region in REGIONS:
        if args.only and region.name not in args.only:
            continue
        shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                          crs=region.crs, dtm_source=region.dtm_source,
                          fetch=region.fetch, workers=args.workers,
                          cache_dir=args.cache_dir)
