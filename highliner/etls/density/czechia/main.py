"""Czechia CLI adapter for country-scoped density aggregation."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final

import highliner.etls.density.shared as shared
from highliner.core import config

COUNTRY: Final[str] = "czechia"
__all__ = ["main", "shared"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-density-czechia")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--workers", type=int, default=1,
                        help="number of pair-file batches to aggregate concurrently")
    args = parser.parse_args(argv)
    shared.build_country_density(country=COUNTRY, data_dir=args.data_dir,
                                 workers=args.workers)


if __name__ == "__main__":
    main()
