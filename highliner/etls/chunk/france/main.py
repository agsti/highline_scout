"""France-specific configuration and CLI for chunk precompute."""
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
from highliner.etls.chunk.france import dtm_rgealti
from highliner.etls.chunk.shared import Bbox

COUNTRY: Final[str] = "france"
# Lambert-93: the single national metric CRS the RGE ALTI 5M dalles are
# published in for every metropolitan department including Corsica, so chunks
# are read without any reprojection or resampling. Overseas departments use
# other CRSs and are out of scope here.
_FRANCE_CRS: Final[str] = "EPSG:2154"


@dataclass(frozen=True)
class Region:
    """One France precompute target and its terrain source configuration."""

    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


def _region(name: str, bbox: Bbox) -> Region:
    return Region(name, bbox, _FRANCE_CRS, "rgealti", dtm_rgealti.fetch)


# Bboxes are ADMIN EXPRESS COG CARTO administrative region bounds (IGN
# Géoplateforme WFS, natively EPSG:2154) rounded outward to 1 km, ordered
# smallest region first. Metropolitan France only.
REGIONS: tuple[Region, ...] = (
    _region("corse", (1156000, 6046000, 1243000, 6236000)),
    _region("ile_de_france", (586000, 6780000, 742000, 6906000)),
    _region("hauts_de_france", (583000, 6859000, 791000, 7111000)),
    _region("bretagne", (99000, 6704000, 401000, 6886000)),
    _region("normandie", (342000, 6788000, 613000, 6999000)),
    _region("provence_alpes_cote_d_azur", (799000, 6214000, 1078000, 6454000)),
    _region("centre_val_de_loire", (476000, 6584000, 710000, 6873000)),
    _region("pays_de_la_loire", (276000, 6582000, 546000, 6835000)),
    _region("bourgogne_franche_comte", (688000, 6562000, 1012000, 6812000)),
    _region("grand_est", (728000, 6710000, 1083000, 7010000)),
    _region("auvergne_rhone_alpes", (626000, 6338000, 1028000, 6634000)),
    _region("occitanie", (428000, 6137000, 849000, 6440000)),
    _region("nouvelle_aquitaine", (311000, 6193000, 670000, 6680000)),
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk-france")
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
