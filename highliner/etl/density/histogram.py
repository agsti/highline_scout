"""Shared bucket and restriction-mask rules for density cells."""
import math
from collections.abc import Iterable

from highliner.core import config

BUCKET_M = config.DENSITY_BUCKET_M
LAYER_BITS = {"zepa": 1, "zec": 2, "enp": 4}


def bucket_for(value: float) -> int:
    """Return the 10 m bucket containing ``value``."""
    return int(value // BUCKET_M)


def bucket_overlaps(bucket: int, minimum: float, maximum: float) -> bool:
    """Whether bucket survives bounds snapped upward to 10 m."""
    return (math.ceil(minimum / BUCKET_M)
            <= bucket < math.ceil(maximum / BUCKET_M))


def layer_mask(layer_ids: Iterable[str]) -> int:
    """Return the bit mask for known restriction-layer IDs."""
    return sum(LAYER_BITS.get(layer_id, 0) for layer_id in layer_ids)


def is_excluded(mask: int, excluded_mask: int) -> bool:
    """Whether any selected restriction layer applies to a candidate."""
    return bool(mask & excluded_mask)
