import argparse
import time
from collections.abc import Callable
from pathlib import Path

from highliner.core import config
from highliner.etls.density import builder

PROGRESS_INTERVAL_S = 30.0


def _fmt_hms(seconds: float) -> str:
    """Format a duration as H:MM:SS."""
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _make_reporter(
    region: str,
    *,
    interval: float = PROGRESS_INTERVAL_S,
    clock: Callable[[], float] = time.monotonic,
) -> Callable[[int, int], None]:
    """Build a progress callback that prints throttled, region-tagged lines.

    Regions are built concurrently (`just precompute-country-density-8`) and the
    processes share one terminal, so lines are newline-terminated rather than
    `\\r`-redrawn: a redraw would be clobbered by the other regions. Throttling
    keeps eight interleaved streams readable.
    """
    start = clock()
    last: float | None = None

    def report(done: int, total: int) -> None:
        nonlocal last
        now = clock()
        if last is not None and done < total and now - last < interval:
            return
        last = now
        pct = 100.0 * done / total if total else 100.0
        print(f"[{region}] pairs file {done}/{total} ({pct:4.1f}%)  "
              f"elapsed {_fmt_hms(now - start)}", flush=True)

    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-density")
    parser.add_argument("--data-dir", default=str(config.DATA_DIR))
    parser.add_argument("--region", required=True)
    parser.add_argument("--country", default=config.DEFAULT_COUNTRY)
    parser.add_argument("--workers", type=int, default=1,
                        help="number of pair-file batches to aggregate concurrently")
    args = parser.parse_args(argv)
    rdir = Path(args.data_dir) / args.country / args.region

    restrictions_dir = Path(args.data_dir) / args.country / "restrictions"
    n = builder.build_density(rdir, report=_make_reporter(args.region),
                              restrictions_dir=restrictions_dir,
                              workers=args.workers)
    print(f"[{args.region}] wrote {n} density cells -> {rdir / 'density'}",
          flush=True)
