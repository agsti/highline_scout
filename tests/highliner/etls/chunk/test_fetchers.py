"""Cross-country contracts for the DTM fetchers each Region carries.

These guard the two failure modes the per-country tests cannot see: a Region
pointing at another country's fetcher, and a fetcher that cannot cross the
process-pool boundary.
"""
import functools
import pickle
from typing import Protocol

import pytest

from highliner.etls.chunk import shared
from highliner.etls.chunk.austria import main as austria
from highliner.etls.chunk.czechia import main as czechia
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.france import main as france
from highliner.etls.chunk.italy import main as italy
from highliner.etls.chunk.poland import main as poland
from highliner.etls.chunk.spain import main as spain
from highliner.etls.chunk.switzerland import main as switzerland
from highliner.etls.chunk.united_kingdom import main as united_kingdom


class RegionLike(Protocol):
    """The subset of every country's Region this file asserts on.

    Each country declares its own Region dataclass, so there is no shared type
    to annotate with — this Protocol is what lets mypy check `.fetch` access
    across all eight.
    """

    name: str
    fetch: Fetcher


COUNTRIES = (
    ("austria", austria),
    ("czechia", czechia),
    ("france", france),
    ("italy", italy),
    ("poland", poland),
    ("spain", spain),
    ("switzerland", switzerland),
    ("united_kingdom", united_kingdom),
)

CASES: list[tuple[str, RegionLike]] = [
    (country, region)
    for country, module in COUNTRIES
    for region in module.REGIONS]
IDS = [f"{country}-{region.name}" for country, region in CASES]


@pytest.mark.parametrize(("country", "region"), CASES, ids=IDS)
def test_region_fetcher_comes_from_its_own_country_package(
        country: str, region: RegionLike) -> None:
    """A region must not be wired to another country's terrain: doing so
    silently produces wrong anchors instead of failing the run."""
    expected = f"highliner.etls.chunk.{country}."
    assert region.fetch.__module__.startswith(expected), (
        f"{country}/{region.name} uses {region.fetch.__module__}")


@pytest.mark.parametrize(("country", "region"), CASES, ids=IDS)
def test_region_fetcher_survives_the_process_pool_boundary(
        country: str, region: RegionLike) -> None:
    """precompute ships functools.partial(process_chunk, fetch=...) into a
    ProcessPoolExecutor. A lambda or nested function pickles fine at
    --workers 1 and raises only under parallelism, so pin it here."""
    payload = pickle.dumps(
        functools.partial(shared.process_chunk, fetch=region.fetch))
    assert pickle.loads(payload).keywords["fetch"] is region.fetch
