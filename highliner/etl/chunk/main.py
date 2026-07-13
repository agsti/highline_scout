import argparse
import time
from pathlib import Path

from highliner.core import config
from highliner.core.regions import defaults_for_region, region_dir
from highliner.etl.chunk import precompute as precompute_service


def _fmt_hms(seconds: float) -> str:
    """Format a duration as H:MM:SS."""
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-chunk")
    parser.add_argument("--data-dir", default=str(config.DATA_DIR))
    parser.add_argument("--region", required=True)
    parser.add_argument("--bbox", required=True,
                        help="minx,miny,maxx,maxy in the region's CRS")
    parser.add_argument("--chunk-km", type=float, default=10.0)
    parser.add_argument("--crs", help="projected CRS for bbox and stored data")
    parser.add_argument("--dtm-source", choices=["icgc", "idee", "cnig"],
                        help="terrain source; defaults from the region name")
    parser.add_argument("--workers", type=int, default=1,
                        help="number of chunks to precompute concurrently")
    args = parser.parse_args(argv)
    minx, miny, maxx, maxy = (float(v) for v in args.bbox.split(","))
    bbox = (minx, miny, maxx, maxy)
    defaults = defaults_for_region(args.region)
    start = time.monotonic()

    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - start
        pct = 100.0 * done / total if total else 100.0
        eta = elapsed / done * (total - done) if done else 0.0
        print(f"\rchunk {done}/{total} ({pct:4.1f}%)  "
              f"elapsed {_fmt_hms(elapsed)}  eta {_fmt_hms(eta)}",
              end="", flush=True)

    data_dir = Path(args.data_dir)
    n = precompute_service.precompute(
        args.region, bbox, data_dir, chunk_m=args.chunk_km * 1000.0,
        report=report, crs=args.crs or defaults.crs,
        dtm_source=args.dtm_source or defaults.dtm_source, workers=args.workers)
    print(f"\nprocessed {n} chunks -> {region_dir(data_dir, args.region)}")
