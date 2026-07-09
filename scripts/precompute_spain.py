"""Run precompute for the non-Catalonia Spain regions.

This is intentionally a thin orchestration wrapper around the public
``highliner`` CLI, so each region remains resumable through the normal chunk
partition skip behavior.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Region:
    name: str
    bbox: str


REGIONS = [
    Region("ceuta", "285000,3972000,295000,3978000"),
    Region("melilla", "502000,3902000,507000,3909000"),
    Region("cantabria", "349000,4734000,488000,4819000"),
    Region("la_rioja", "488000,4641000,610000,4722000"),
    Region("pais_vasco", "463000,4702000,604000,4812000"),
    Region("asturias", "161000,4754000,378000,4839000"),
    Region("madrid", "365000,4415000,496000,4558000"),
    Region("navarra", "540000,4640000,686000,4797000"),
    Region("murcia", "557000,4137000,708000,4292000"),
    Region("galicia", "-15000,4637000,193000,4860000"),
    Region("illes_balears", "860000,4286000,1127000,4463000"),
    Region("comunitat_valenciana", "626000,4190000,816000,4520000"),
    Region("extremadura", "110000,4204000,358000,4487000"),
    Region("aragon", "569000,4412000,811000,4755000"),
    Region("canarias", "188000,3060000,662000,3256000"),
    Region("castilla_la_mancha", "294000,4208000,682000,4576000"),
    Region("castilla_y_leon", "165000,4439000,602000,4790000"),
    Region("andalucia", "100000,3977000,622000,4289000"),
    Region("catalonia2", "399134,4603853,403346,4607126"),
]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def run_region(region: Region, highliner: str, data_dir: str,
               chunk_workers: int) -> None:
    run([highliner, "precompute", "--data-dir", data_dir,
         "--region", region.name, f"--bbox={region.bbox}",
         "--workers", str(chunk_workers)])
    run([highliner, "precompute-density", "--data-dir", data_dir,
         "--region", region.name])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--start-at", help="skip regions before this id")
    parser.add_argument("--only", action="append", help="run only this region id")
    parser.add_argument("--jobs", type=int, default=1,
                        help="number of regions to precompute concurrently")
    parser.add_argument("--chunk-workers", type=int, default=1,
                        help="number of chunks to precompute concurrently per region")
    args = parser.parse_args()

    regions = REGIONS
    if args.start_at:
        names = [r.name for r in regions]
        if args.start_at not in names:
            raise SystemExit(f"unknown region for --start-at: {args.start_at}")
        regions = regions[names.index(args.start_at):]
    if args.only:
        wanted = set(args.only)
        regions = [r for r in regions if r.name in wanted]

    highliner = str(Path(".venv/bin/highliner"))
    if args.jobs < 1:
        raise SystemExit("--jobs must be >= 1")
    if args.chunk_workers < 1:
        raise SystemExit("--chunk-workers must be >= 1")
    if args.jobs == 1:
        for region in regions:
            run_region(region, highliner, args.data_dir, args.chunk_workers)
        return

    print(f"running {len(regions)} regions with {args.jobs} jobs "
          f"and {args.chunk_workers} chunk workers each", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(run_region, region, highliner, args.data_dir,
                        args.chunk_workers): region
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


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
