"""Canada CLI adapter for the NRCan HRDEM terrain source."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.canada import dtm_hrdem
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "canada"
_CRS: Final[str] = "EPSG:3979"


@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


def _region(name: str, bbox: Bbox) -> Region:
    return Region(name, bbox, _CRS, "hrdem", dtm_hrdem.fetch)


# Statistics Canada 2021 provincial/territorial boundaries, reprojected to the
# native Canada Atlas Lambert CRS and rounded outward to 1 km.
REGIONS: tuple[Region, ...] = (
    _region("alberta", (-1826000, 20000, -806000, 1468000)),
    _region("british_columbia", (-3040000, 99000, -1015000, 1998000)),
    _region("manitoba", (-512000, 20000, 439000, 1333000)),
    _region("new_brunswick", (1849000, -29000, 2461000, 577000)),
    _region("newfoundland_and_labrador", (1376000, 107000, 3123000, 2048000)),
    _region("northwest_territories", (-2117000, 1225000, -150000, 3570000)),
    _region("nova_scotia", (2078000, -168000, 2859000, 538000)),
    _region("nunavut", (-1762000, 586000, 2259000, 3971000)),
    _region("ontario", (-88000, -905000, 1803000, 1083000)),
    _region("prince_edward_island", (2239000, 207000, 2500000, 446000)),
    _region("quebec", (730000, -308000, 2871000, 2071000)),
    _region("saskatchewan", (-1088000, 20000, -324000, 1300000)),
    _region("yukon", (-2284000, 1533000, -1008000, 2880000)),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-canada")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at")
    parser.add_argument("--only", action="append")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args(argv)


def _select_regions(start_at: str | None, only: list[str] | None) -> tuple[Region, ...]:
    regions = REGIONS
    if start_at:
        names = [region.name for region in regions]
        if start_at not in names:
            raise SystemExit(f"unknown region for --start-at: {start_at}")
        regions = regions[names.index(start_at):]
    if only:
        regions = tuple(region for region in regions if region.name in set(only))
    return regions


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    for region in _select_regions(args.start_at, args.only):
        start = time.monotonic()
        print(f"[{region.name}] starting precompute", flush=True)
        count = shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                                  crs=region.crs, dtm_source=region.dtm_source,
                                  fetch=region.fetch, workers=args.workers,
                                  cache_dir=args.cache_dir)
        print(f"[{region.name}] completed {count} chunks -> "
              f"{shared.region_output_dir(args.data_dir, COUNTRY, region.name)} "
              f"in {int(time.monotonic() - start)}s", flush=True)
