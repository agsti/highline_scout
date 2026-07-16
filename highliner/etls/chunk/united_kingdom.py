"""United Kingdom configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "united_kingdom"


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str


# Rounded-out projected administrative extents. OS Terrain 50 covers Great
# Britain; OSNI's open DTM fills the separate Northern Ireland grid.
REGIONS: tuple[Region, ...] = (
    Region("england", (70000, 0, 660000, 660000), "EPSG:27700", "os_terrain_50"),
    Region("wales", (140000, 0, 360000, 410000), "EPSG:27700", "os_terrain_50"),
    Region("scotland", (0, 530000, 500000, 1220000), "EPSG:27700", "os_terrain_50"),
    Region("northern_ireland", (200000, 220000, 390000, 460000), "EPSG:29903",
           "osni_dtm_10m"),
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at", help="skip regions before this id")
    parser.add_argument("--only", action="append", help="run only this region id")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.jobs != 1:
        raise SystemExit("--jobs > 1 is not supported for this adapter")
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    regions = REGIONS
    if args.start_at:
        names = [region.name for region in regions]
        if args.start_at not in names:
            raise SystemExit(f"unknown region for --start-at: {args.start_at}")
        regions = regions[names.index(args.start_at):]
    if args.only:
        wanted = set(args.only)
        regions = tuple(region for region in regions if region.name in wanted)
    for region in regions:
        shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                          crs=region.crs, dtm_source=region.dtm_source,
                          workers=args.workers, cache_dir=args.cache_dir)


if __name__ == "__main__":
    main()
