"""Cyprus CLI adapter for country-scoped density aggregation."""
import argparse
from pathlib import Path
from typing import Final

import highliner.etls.density.shared as shared
from highliner.core import config

COUNTRY: Final[str] = "cyprus"
__all__ = ["main", "shared"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-density-cyprus")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    shared.build_country_density(country=COUNTRY, data_dir=args.data_dir,
                                 workers=args.workers)
