"""French Polynesia configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.french_polynesia import dtm_daf
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "french_polynesia"
__all__ = ["main", "shared", "dtm_daf", "config"]


@dataclass(frozen=True)
class Region:
    """One French Polynesian island with a compatible bare-earth MNT."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# The DAF 2015 lidar MNT extents, rounded outward to 1 km in their native RGPF
# UTM zones.  They are the territory-wide source's explicitly lidar-derived
# islands; lower-quality photogrammetric products are intentionally excluded.
REGIONS: tuple[Region, ...] = (
    Region("moorea", (187000, 8049000, 210000, 8068000), "EPSG:3297",
           "daf_lidar_mnt", dtm_daf.fetch),
    Region("tahiti", (219000, 8034000, 248000, 8067000), "EPSG:3297",
           "daf_lidar_mnt", dtm_daf.fetch),
    Region("bora_bora", (627000, 8168000, 642000, 8183000), "EPSG:3296",
           "daf_lidar_mnt", dtm_daf.fetch),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-french-polynesia")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--only", action="append", help="run only this island id")
    parser.add_argument("--workers", type=int, default=1,
                        help="number of chunks to precompute concurrently")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Precompute the available French Polynesian island MNTs."""
    args = _parse_args(argv)
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    wanted = set(args.only or ())
    regions = tuple(region for region in REGIONS if not wanted or region.name in wanted)
    for region in regions:
        shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                          crs=region.crs, dtm_source=region.dtm_source,
                          fetch=region.fetch, workers=args.workers,
                          cache_dir=args.cache_dir)


if __name__ == "__main__":
    main()
