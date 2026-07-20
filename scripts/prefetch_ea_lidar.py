"""Prefetch the EA lidar composite into the United Kingdom terrain cache.

Downloads every 5 km EA tile intersecting a bbox (England's envelope by
default), resampling each to 5 m as it lands, so a later
``just etl-chunk united_kingdom N`` reads terrain purely from cache instead
of interleaving ~370 GB of downloads with chunk processing. Safe to
interrupt and re-run: cached tiles and known-missing (sea/gap) tiles are
skipped, and concurrent runs are serialized per tile by file locks.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import sys
from pathlib import Path

from highliner.core import config
from highliner.etls.chunk.united_kingdom import dtm_ea
from highliner.etls.chunk.united_kingdom import main as united_kingdom

COUNTRY = "united_kingdom"
_PROGRESS_EVERY = 100


def _england_bbox() -> tuple[float, float, float, float]:
    return next(r.bbox for r in united_kingdom.REGIONS if r.name == "england")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prefetch-ea-lidar")
    parser.add_argument("--cache-dir", type=Path, default=config.CACHE_DIR,
                        help="cache root; tiles land under "
                             f"<cache-dir>/{COUNTRY}/ea-lidar-5m")
    parser.add_argument("--bbox", type=float, nargs=4,
                        metavar=("MINX", "MINY", "MAXX", "MAXY"),
                        default=None,
                        help="EPSG:27700 bbox (default: England envelope)")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    bbox = tuple(args.bbox) if args.bbox else _england_bbox()
    cache_root = args.cache_dir / COUNTRY
    tiles = dtm_ea.tile_ids(bbox)  # type: ignore[arg-type]
    print(f"{len(tiles)} tiles cover bbox {bbox}", flush=True)

    fetched = missing = failed = 0
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(dtm_ea.ensure_tile, t, cache_root): t
                   for t in tiles}
        for done, future in enumerate(
                concurrent.futures.as_completed(futures), start=1):
            try:
                path = future.result()
            except Exception as exc:      # noqa: BLE001 — keep prefetching
                failed += 1
                print(f"{futures[future]}: {exc}", file=sys.stderr, flush=True)
            else:
                if path is None:
                    missing += 1
                else:
                    fetched += 1
            if done % _PROGRESS_EVERY == 0 or done == len(tiles):
                print(f"{done}/{len(tiles)} — {fetched} cached, "
                      f"{missing} missing, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
