"""Read precomputed pair partitions for offline density aggregation."""
from pathlib import Path

from highliner.models.candidate import Candidate
from highliner.server.repositories.partition_cache import read_pair_columns


def load_candidates(path: str | Path) -> list[Candidate]:
    """Materialize every pair in one partition for a single offline pass."""
    return read_pair_columns(path).to_candidates()
