"""Read candidate pairs from parquet partitions (read side).

The write side (`save_candidates`) and the stored-column layout live in
`highliner.etl.repositories.candidates`. Serve-time reads go through the cached,
columnar path in `highliner.server.repositories.partition_cache`; this whole-file
materializer is kept for the offline density aggregation, which streams every
partition exactly once (so caching would only waste memory).
"""
from pathlib import Path

from highliner.models.candidate import Candidate
from highliner.server.repositories.partition_cache import read_pair_columns


def load_candidates(path: str | Path) -> list[Candidate]:
    return read_pair_columns(path).to_candidates()
