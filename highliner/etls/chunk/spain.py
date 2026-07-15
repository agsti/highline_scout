"""Spain-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "spain"
_PENINSULA_CRS: Final[str] = "EPSG:25830"
_CATALONIA_CRS: Final[str] = "EPSG:25831"
_CANARIES_CRS: Final[str] = "EPSG:4083"


@dataclass(frozen=True)
class Region:
    """One Spain precompute target and its terrain source configuration."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str


def _peninsula(name: str, bbox: Bbox) -> Region:
    return Region(name, bbox, _PENINSULA_CRS, "cnig")


REGIONS: tuple[Region, ...] = (
    _peninsula("ceuta", (285000, 3972000, 295000, 3978000)),
    _peninsula("melilla", (502000, 3902000, 507000, 3909000)),
    _peninsula("cantabria", (349000, 4734000, 488000, 4819000)),
    _peninsula("la_rioja", (488000, 4641000, 610000, 4722000)),
    _peninsula("pais_vasco", (463000, 4702000, 604000, 4812000)),
    _peninsula("asturias", (161000, 4754000, 378000, 4839000)),
    _peninsula("madrid", (365000, 4415000, 496000, 4558000)),
    _peninsula("navarra", (540000, 4640000, 686000, 4797000)),
    _peninsula("murcia", (557000, 4137000, 708000, 4292000)),
    _peninsula("galicia", (-15000, 4637000, 193000, 4860000)),
    _peninsula("illes_balears", (860000, 4286000, 1127000, 4463000)),
    _peninsula("comunitat_valenciana", (626000, 4190000, 816000, 4520000)),
    _peninsula("extremadura", (110000, 4204000, 358000, 4487000)),
    _peninsula("aragon", (569000, 4412000, 811000, 4755000)),
    Region("canarias", (188000, 3060000, 662000, 3256000), _CANARIES_CRS, "cnig"),
    _peninsula("castilla_la_mancha", (294000, 4208000, 682000, 4576000)),
    _peninsula("castilla_y_leon", (165000, 4439000, 602000, 4790000)),
    _peninsula("andalucia", (100000, 3977000, 622000, 4289000)),
    Region("catalonia2", (399134, 4603853, 403346, 4607126), _CATALONIA_CRS, "icgc"),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR)
    parser.add_argument("--start-at", help="skip regions before this id")
    parser.add_argument("--only", action="append", help="run only this region id")
    parser.add_argument("--jobs", type=int, default=1,
                        help="number of regions to precompute concurrently")
    parser.add_argument("--workers", type=int, default=1,
                        help="number of chunks to precompute concurrently per region")
    return parser.parse_args(argv)


def _select_regions(start_at: str | None, only: list[str] | None) -> tuple[Region, ...]:
    regions = REGIONS
    if start_at:
        names = [region.name for region in regions]
        if start_at not in names:
            raise SystemExit(f"unknown region for --start-at: {start_at}")
        regions = regions[names.index(start_at):]
    if only:
        wanted = set(only)
        regions = tuple(region for region in regions if region.name in wanted)
    return regions


def _precompute_region(region: Region, data_dir: Path, cache_dir: Path,
                       workers: int) -> int:
    return shared.precompute(
        COUNTRY, region.name, region.bbox, data_dir, crs=region.crs,
        dtm_source=region.dtm_source, workers=workers, cache_dir=cache_dir)


def _run_parallel(regions: tuple[Region, ...], data_dir: Path, cache_dir: Path,
                  jobs: int, workers: int) -> None:
    print(f"running {len(regions)} regions with {jobs} jobs "
          f"and {workers} chunk workers each", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(_precompute_region, region, data_dir, cache_dir, workers):
                region
            for region in regions
        }
        for future in concurrent.futures.as_completed(futures):
            region = futures[future]
            try:
                future.result()
            except Exception as exc:
                for pending in futures:
                    pending.cancel()
                raise RuntimeError(f"{region.name} failed") from exc


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.jobs < 1:
        raise SystemExit("--jobs must be >= 1")
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")

    regions = _select_regions(args.start_at, args.only)
    if args.jobs == 1:
        for region in regions:
            _precompute_region(region, args.data_dir, args.cache_dir, args.workers)
        return
    _run_parallel(regions, args.data_dir, args.cache_dir, args.jobs, args.workers)


if __name__ == "__main__":
    main()
