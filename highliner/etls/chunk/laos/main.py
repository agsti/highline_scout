"""Laos configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.laos import dtm_world_bank
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "laos"
__all__ = ["main", "shared"]


@dataclass(frozen=True)
class Region:
    """One Laos precompute target and its terrain source configuration."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# The World Bank's 2021 drone-derived DTM covers Luang Prabang only. Bounds
# are its EPSG:32648 GeoTIFF extent, rounded outward to 1 km.
REGIONS: tuple[Region, ...] = (
    Region("luang_prabang", (196000, 2198000, 207000, 2206000), "EPSG:32648",
           "world_bank_luang_prabang_2021", dtm_world_bank.fetch),
)


def main(argv: list[str] | None = None) -> None:
    """Precompute the available high-resolution Laos terrain region."""
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-laos")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--only", action="append", help="run only this region id")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    wanted = set(args.only or ())
    for region in REGIONS:
        if wanted and region.name not in wanted:
            continue
        shared.precompute(
            COUNTRY, region.name, region.bbox, args.data_dir, crs=region.crs,
            dtm_source=region.dtm_source, fetch=region.fetch,
            workers=args.workers, cache_dir=args.cache_dir)
