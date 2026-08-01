from pathlib import Path

import pytest


def test_belgium_registers_flanders_and_wallonia() -> None:
    from highliner.etls.chunk.belgium import main

    regions = [(region.name, region.crs, region.dtm_source)
               for region in main.REGIONS]
    assert regions == [
        ("flanders", "EPSG:31370", "dhmv_ii"),
        ("wallonia", "EPSG:3812", "wallonia_mnt_2021_2022"),
    ]


def test_dhmv_fetch_requires_lambert_72(tmp_path: Path) -> None:
    from highliner.etls.chunk.belgium import dtm_dhmv

    with pytest.raises(ValueError, match="EPSG:31370"):
        dtm_dhmv.fetch((0, 0, 1, 1), tmp_path, None, "EPSG:4326")
