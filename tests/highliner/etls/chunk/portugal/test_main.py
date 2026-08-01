import functools
import pickle

from highliner.etls.chunk import shared
from highliner.etls.chunk.portugal import main as portugal


def test_portugal_covers_mainland_in_pt_tm06() -> None:
    assert [region.name for region in portugal.REGIONS] == ["mainland"]
    region = portugal.REGIONS[0]
    assert region.crs == "EPSG:3763"
    assert region.dtm_source == "dgt_mdt_2m"
    assert region.bbox == (-131000, -307000, 168000, 284000)


def test_portugal_fetcher_survives_the_process_pool_boundary() -> None:
    fetch = portugal.REGIONS[0].fetch
    payload = pickle.dumps(functools.partial(shared.process_chunk, fetch=fetch))
    assert pickle.loads(payload).keywords["fetch"] is fetch
