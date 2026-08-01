"""French Polynesia adapter for country-scoped density aggregation."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final

from highliner.core import config
from highliner.etls.density import shared

COUNTRY: Final[str] = "french_polynesia"
__all__ = ["main", "shared"]


def main(argv: list[str] | None = None) -> None:
    """Build density layers for all precomputed French Polynesian islands."""
    parser = argparse.ArgumentParser(prog="highliner-etl-density-french-polynesia")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    shared.build_country_density(country=COUNTRY, data_dir=args.data_dir,
                                 workers=args.workers)
