from highliner.models.candidate import Candidate


def filter_candidates(candidates: list[Candidate], max_len: float, min_len: float,
                      min_exposure: float, max_dh: float) -> list[Candidate]:
    """Narrow precomputed candidates by the live slider thresholds."""
    return [c for c in candidates
            if min_len <= c.length <= max_len
            and c.exposure >= min_exposure
            and c.height_diff <= max_dh]
