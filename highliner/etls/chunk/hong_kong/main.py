"""Hong Kong chunk-precompute configuration and CLI."""
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.hong_kong import dtm_landsd
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "hong_kong"


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


# Hong Kong boundary in HK1980 Grid (EPSG:2326), rounded out to kilometres.
REGION = Region("hong_kong", (790000, 790000, 880000, 850000), "EPSG:2326",
                "landsd_dtm_5m", dtm_landsd.fetch)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-hong-kong")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--only", action="append")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    if args.only and REGION.name not in args.only:
        return
    shared.precompute(COUNTRY, REGION.name, REGION.bbox, args.data_dir,
                      crs=REGION.crs, dtm_source=REGION.dtm_source,
                      fetch=REGION.fetch, workers=args.workers,
                      cache_dir=args.cache_dir)
