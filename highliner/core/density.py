"""Shared histogram rules for offline density generation and serving."""
import math
from collections.abc import Iterable

from highliner.core import config

BUCKET_M = config.DENSITY_BUCKET_M
LAYER_BITS = {
    "zepa": 1,
    "zec": 2,
    "enp": 4,
    "zps": 8,
    "zsc": 16,
    "euap": 32,
    "fr_zps": 64,
    "fr_zsc": 128,
    "fr_ep": 256,
    "ch_game_reserves": 512,
    "ch_bird_reserves": 1024,
    "ch_parks": 2048,
    "cl_snaspe": 4096,
    "cl_santuario": 8192,
    "cl_conservacion_privada": 16384,
    "hk_country_parks": 32768,
}


def bucket_for(value: float) -> int:
    """Return the 10 m bucket containing a value."""
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
