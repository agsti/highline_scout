"""Switzerland-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "switzerland"
_SWITZERLAND_CRS: Final[str] = "EPSG:2056"


@dataclass(frozen=True)
class Region:
    """One Switzerland precompute target and its terrain source."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str


# Swiss national territory extent from swisstopo swissBOUNDARIES3D 2026,
# natively LV95/LN02 and rounded outward to 1 km. One national region avoids
# duplicate terrain work from overlapping canton bounding boxes.
REGIONS: tuple[Region, ...] = (
    Region("switzerland", (2485000, 1075000, 2834000, 1296000),
           _SWITZERLAND_CRS, "swissalti3d"),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-switzerland")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at", help="skip regions before this id")
    parser.add_argument("--only", action="append", help="run only this region id")
    parser.add_argument("--jobs", type=int, default=1,
                        help="number of regions to precompute concurrently")
    parser.add_argument("--workers", type=int, default=1,
                        help="number of chunks to precompute concurrently per region")
    return parser.parse_args(argv)


def _select_regions(start_at: str | None,
                    only: list[str] | None) -> tuple[Region, ...]:
    if start_at and start_at != "switzerland":
        raise SystemExit(f"unknown region for --start-at: {start_at}")
    if only and "switzerland" not in set(only):
        return ()
    return REGIONS


def _fmt_hms(seconds: float) -> str:
    seconds_int = int(seconds)
    return (f"{seconds_int // 3600}:"
            f"{(seconds_int % 3600) // 60:02d}:{seconds_int % 60:02d}")


def _precompute(region: Region, data_dir: Path, cache_dir: Path,
                workers: int) -> None:
    print(f"[{region.name}] starting precompute", flush=True)
    start = time.monotonic()

    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - start
        pct = 100.0 * done / total if total else 100.0
        eta = elapsed / done * (total - done) if done else 0.0
        print(f"\rchunk {done}/{total} ({pct:4.1f}%)  "
              f"elapsed {_fmt_hms(elapsed)}  eta {_fmt_hms(eta)}",
              end="", flush=True)

    count = shared.precompute(
        COUNTRY, region.name, region.bbox, data_dir, crs=region.crs,
        dtm_source=region.dtm_source, workers=workers, cache_dir=cache_dir,
        report=report)
    print()
    print(f"[{region.name}] completed {count} chunks -> "
          f"{shared.region_output_dir(data_dir, COUNTRY, region.name)}", flush=True)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1 or args.workers < 1:
        raise SystemExit("--jobs and --workers must be >= 1")
    for region in _select_regions(args.start_at, args.only):
        _precompute(region, args.data_dir, args.cache_dir, args.workers)


if __name__ == "__main__":
    main()
