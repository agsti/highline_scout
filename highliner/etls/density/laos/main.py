"""Laos CLI adapter for density aggregation."""
import argparse
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.density import shared

COUNTRY: Final[str] = "laos"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-density-laos")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    shared.build_country_density(COUNTRY, args.data_dir, args.workers)
