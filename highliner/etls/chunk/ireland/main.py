"""Ireland configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.ireland import dtm_gsi
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "ireland"


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# GSI Phase 2 1 m LiDAR coverage envelope, in Irish Transverse Mercator and
# rounded outward to kilometres. The source catalogue omits its coverage gaps.
REGIONS = (Region("ireland", (512_000, 694_000, 604_000, 768_000), "EPSG:2157",
                  "gsi_lidar_dtm_1m", dtm_gsi.fetch),)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-ireland")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--only", action="append")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    regions = tuple(region for region in REGIONS
                    if not args.only or region.name in set(args.only))
    for region in regions:
        shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                          crs=region.crs, dtm_source=region.dtm_source,
                          fetch=region.fetch, workers=args.workers,
                          cache_dir=args.cache_dir)
