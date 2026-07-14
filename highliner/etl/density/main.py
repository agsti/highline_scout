import argparse
import time
from pathlib import Path

from highliner.core import config
from highliner.etl.density import builder


def _fmt_hms(seconds: float) -> str:
    """Format a duration as H:MM:SS."""
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-density")
    parser.add_argument("--data-dir", default=str(config.DATA_DIR))
    parser.add_argument("--region", required=True)
    parser.add_argument("--country", default=config.DEFAULT_COUNTRY)
    parser.add_argument("--workers", type=int, default=1,
                        help="number of pair-file batches to aggregate concurrently")
    args = parser.parse_args(argv)
    rdir = Path(args.data_dir) / args.country / args.region
    start = time.monotonic()

    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - start
        pct = 100.0 * done / total if total else 100.0
        print(f"\rpairs file {done}/{total} ({pct:4.1f}%)  "
              f"elapsed {_fmt_hms(elapsed)}", end="", flush=True)

    restrictions_dir = Path(args.data_dir) / args.country / "restrictions"
    n = builder.build_density(rdir, report=report,
                              restrictions_dir=restrictions_dir,
                              workers=args.workers)
    print(f"\nwrote {n} density cells -> {rdir / 'density'}")
