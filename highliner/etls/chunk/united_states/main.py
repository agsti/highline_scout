"""United States-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import concurrent.futures
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.shared import Bbox
from highliner.etls.chunk.united_states import dtm_3dep

COUNTRY: Final[str] = "united_states"

# One metric projected CRS per macro-region.  CONUS rides NAD83 Conus Albers
# (equal-area, metres); its <~1% distance distortion is negligible for the
# local slope/exposure geometry.  Alaska and Hawaii fall outside that projection
# and get their own.
_CONUS_CRS: Final[str] = "EPSG:5070"
_ALASKA_CRS: Final[str] = "EPSG:3338"
_HAWAII_CRS: Final[str] = "EPSG:32604"


@dataclass(frozen=True)
class Region:
    """One United States precompute target and its terrain source configuration."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


def _region(name: str, bbox: Bbox, crs: str) -> Region:
    return Region(name, bbox, crs, "3dep", dtm_3dep.fetch)


# 50 states + DC.  Bboxes are each state's Census 2021 geometry reprojected to
# its region CRS and rounded outward to the nearest 1 km.  Every region draws
# terrain from the one national 3DEP ImageServer.  Territories (Puerto Rico
# etc.) are tracked under their own issues, not here.
REGIONS: tuple[Region, ...] = (
    _region("alabama", (704000, 828000, 1045000, 1377000), _CONUS_CRS),
    _region("alaska", (-2169000, 413000, 1493000, 2375000), _ALASKA_CRS),
    _region("arizona", (-1747000, 1002000, -1146000, 1702000), _CONUS_CRS),
    _region("arkansas", (122000, 1107000, 568000, 1511000), _CONUS_CRS),
    _region("california", (-2357000, 1243000, -1646000, 2453000), _CONUS_CRS),
    _region("colorado", (-1147000, 1566000, -504000, 2074000), _CONUS_CRS),
    _region("connecticut", (1833000, 2215000, 1987000, 2366000), _CONUS_CRS),
    _region("delaware", (1704000, 1901000, 1797000, 2056000), _CONUS_CRS),
    _region("district_of_columbia", (1610000, 1913000, 1630000, 1937000), _CONUS_CRS),
    _region("florida", (796000, 268000, 1603000, 961000), _CONUS_CRS),
    _region("georgia", (939000, 906000, 1420000, 1406000), _CONUS_CRS),
    _region("hawaii", (370000, 2094000, 940000, 2459000), _HAWAII_CRS),
    _region("idaho", (-1716000, 2208000, -1189000, 3060000), _CONUS_CRS),
    _region("illinois", (378000, 1570000, 731000, 2195000), _CONUS_CRS),
    _region("indiana", (690000, 1667000, 962000, 2139000), _CONUS_CRS),
    _region("iowa", (-51000, 1938000, 482000, 2289000), _CONUS_CRS),
    _region("kansas", (-533000, 1550000, 122000, 1904000), _CONUS_CRS),
    _region("kentucky", (569000, 1513000, 1224000, 1849000), _CONUS_CRS),
    _region("louisiana", (181000, 673000, 680000, 1116000), _CONUS_CRS),
    _region("maine", (1930000, 2500000, 2259000, 3013000), _CONUS_CRS),
    _region("maryland", (1396000, 1838000, 1797000, 2038000), _CONUS_CRS),
    _region("massachusetts", (1830000, 2302000, 2138000, 2478000), _CONUS_CRS),
    _region("michigan", (429000, 2120000, 1098000, 2825000), _CONUS_CRS),
    _region("minnesota", (-92000, 2278000, 490000, 2931000), _CONUS_CRS),
    _region("mississippi", (413000, 810000, 729000, 1356000), _CONUS_CRS),
    _region("missouri", (19000, 1453000, 609000, 1964000), _CONUS_CRS),
    _region("montana", (-1498000, 2472000, -595000, 3045000), _CONUS_CRS),
    _region("nebraska", (-672000, 1887000, 59000, 2251000), _CONUS_CRS),
    _region("nevada", (-2038000, 1491000, -1475000, 2359000), _CONUS_CRS),
    _region("new_hampshire", (1879000, 2428000, 2026000, 2735000), _CONUS_CRS),
    _region("new_jersey", (1725000, 1966000, 1843000, 2237000), _CONUS_CRS),
    _region("new_mexico", (-1234000, 991000, -616000, 1630000), _CONUS_CRS),
    _region("new_york", (1324000, 2151000, 1992000, 2659000), _CONUS_CRS),
    _region("north_carolina", (1054000, 1345000, 1834000, 1689000), _CONUS_CRS),
    _region("north_dakota", (-624000, 2549000, -42000, 2914000), _CONUS_CRS),
    _region("ohio", (922000, 1790000, 1293000, 2212000), _CONUS_CRS),
    _region("oklahoma", (-621000, 1173000, 142000, 1574000), _CONUS_CRS),
    _region("oregon", (-2295000, 2301000, -1584000, 2900000), _CONUS_CRS),
    _region("pennsylvania", (1268000, 1962000, 1782000, 2295000), _CONUS_CRS),
    _region("rhode_island", (1969000, 2274000, 2038000, 2374000), _CONUS_CRS),
    _region("south_carolina", (1145000, 1108000, 1595000, 1450000), _CONUS_CRS),
    _region("south_dakota", (-653000, 2165000, -35000, 2578000), _CONUS_CRS),
    _region("tennessee", (514000, 1341000, 1268000, 1604000), _CONUS_CRS),
    _region("texas", (-1000000, 311000, 236000, 1518000), _CONUS_CRS),
    _region("utah", (-1582000, 1629000, -1085000, 2251000), _CONUS_CRS),
    _region("vermont", (1766000, 2414000, 1917000, 2695000), _CONUS_CRS),
    _region("virginia", (1089000, 1576000, 1791000, 1967000), _CONUS_CRS),
    _region("washington", (-2139000, 2734000, -1545000, 3166000), _CONUS_CRS),
    _region("west_virginia", (1155000, 1668000, 1552000, 2065000), _CONUS_CRS),
    _region("wisconsin", (242000, 2180000, 719000, 2686000), _CONUS_CRS),
    _region("wyoming", (-1251000, 2027000, -633000, 2540000), _CONUS_CRS),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-united-states")
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


def _fmt_hms(seconds: float) -> str:
    """Format a duration as H:MM:SS."""
    seconds_int = int(seconds)
    return (f"{seconds_int // 3600}:"
            f"{(seconds_int % 3600) // 60:02d}:{seconds_int % 60:02d}")


def _precompute_region(region: Region, data_dir: Path, cache_dir: Path,
                       workers: int) -> int:
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
        dtm_source=region.dtm_source, fetch=region.fetch,
        workers=workers, cache_dir=cache_dir,
        report=report)
    print()
    print(f"[{region.name}] completed {count} chunks -> "
          f"{shared.region_output_dir(data_dir, COUNTRY, region.name)}", flush=True)
    return count


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
