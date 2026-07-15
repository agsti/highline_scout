"""Shared country orchestration for offline density aggregation."""
import time
from collections.abc import Callable
from pathlib import Path

from highliner.etls.density import builder

PROGRESS_INTERVAL_S = 30.0


def _fmt_hms(seconds: float) -> str:
    """Format a duration as H:MM:SS."""
    seconds_int = int(seconds)
    return (f"{seconds_int // 3600}:"
            f"{(seconds_int % 3600) // 60:02d}:{seconds_int % 60:02d}")


def _make_reporter(
    region: str,
    *,
    interval: float = PROGRESS_INTERVAL_S,
    clock: Callable[[], float] = time.monotonic,
) -> Callable[[int, int], None]:
    """Build a throttled, region-tagged progress callback."""
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


def discover_regions(data_dir: Path, country: str) -> list[Path]:
    """Return sorted region directories with precomputed grid metadata."""
    country_dir = Path(data_dir) / country
    if not country_dir.is_dir():
        return []
    return [path for path in sorted(country_dir.iterdir())
            if path.is_dir() and (path / "grid.json").is_file()]


def build_country_density(country: str, data_dir: Path,
                          workers: int = 1) -> dict[str, int]:
    """Build density sequentially for every discovered country region."""
    if workers < 1:
        raise ValueError("workers must be >= 1")
    restrictions_dir = Path(data_dir) / country / "restrictions"
    return {
        region_dir.name: builder.build_density(
            region_dir, report=_make_reporter(region_dir.name),
            restrictions_dir=restrictions_dir, workers=workers)
        for region_dir in discover_regions(data_dir, country)
    }
