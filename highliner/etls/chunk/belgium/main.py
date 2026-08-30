"""Belgium-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.belgium import dtm_dhmv, dtm_wallonie
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "belgium"


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


REGIONS: tuple[Region, ...] = (
    Region("flanders", (17_000, 148_000, 264_000, 250_000), "EPSG:31370",
           "dhmv_ii", dtm_dhmv.fetch),
    Region("wallonia", (542_000, 521_000, 796_000, 668_000), "EPSG:3812",
           "wallonia_mnt_2021_2022", dtm_wallonie.fetch),
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-belgium")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--only", action="append")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    wanted = set(args.only) if args.only else None
    for region in REGIONS:
        if wanted is not None and region.name not in wanted:
            continue
        shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                          crs=region.crs, dtm_source=region.dtm_source,
                          fetch=region.fetch, workers=args.workers,
                          cache_dir=args.cache_dir)
