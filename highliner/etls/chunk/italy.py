"""Italy-specific configuration and CLI for chunk precompute."""
from __future__ import annotations

import argparse
import concurrent.futures
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.chunk import shared as shared
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "italy"
# RDN2008 / Italy zone: the single national metric CRS the HR-DTM-5m grid is
# published in, so chunks are read without any reprojection or resampling.
_ITALY_CRS: Final[str] = "EPSG:6875"


@dataclass(frozen=True)
class Region:
    """One Italy precompute target and its terrain source configuration."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str


def _region(name: str, bbox: Bbox) -> Region:
    return Region(name, bbox, _ITALY_CRS, "hrdtm")


# Bboxes are ISTAT 2025 administrative region bounds ("Limiti01012025_g",
# natively EPSG:32632) reprojected to EPSG:6875 and rounded outward to 1 km,
# ordered smallest region first.
REGIONS: tuple[Region, ...] = (
    _region("valle_d_aosta", (6596000, 5040000, 6685000, 5097000)),
    _region("molise", (7161000, 4577000, 7263000, 4657000)),
    _region("liguria", (6638000, 4850000, 6846000, 4947000)),
    _region("friuli_venezia_giulia", (7024000, 5043000, 7150000, 5161000)),
    _region("umbria", (6991000, 4685000, 7104000, 4825000)),
    _region("marche", (7014000, 4721000, 7157000, 4864000)),
    _region("basilicata", (7280000, 4419000, 7413000, 4557000)),
    _region("abruzzo", (7084000, 4611000, 7231000, 4746000)),
    _region("trentino_alto_adige", (6876000, 5052000, 7037000, 5210000)),
    _region("campania", (7147000, 4427000, 7324000, 4593000)),
    _region("calabria", (7317000, 4198000, 7451000, 4449000)),
    _region("lazio", (6954000, 4510000, 7169000, 4738000)),
    _region("veneto", (6892000, 4954000, 7086000, 5165000)),
    _region("puglia", (7244000, 4419000, 7556000, 4677000)),
    _region("emilia_romagna", (6778000, 4836000, 7061000, 4996000)),
    _region("toscana", (6815000, 4671000, 7030000, 4921000)),
    _region("lombardia", (6725000, 4945000, 6955000, 5161000)),
    _region("sardegna", (6673000, 4302000, 6817000, 4572000)),
    _region("piemonte", (6577000, 4882000, 6780000, 5147000)),
    _region("sicilia", (6993000, 3923000, 7320000, 4297000)),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-italy")
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
        dtm_source=region.dtm_source, workers=workers, cache_dir=cache_dir,
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
