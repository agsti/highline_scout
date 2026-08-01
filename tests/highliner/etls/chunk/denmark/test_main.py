from pathlib import Path
from typing import Any

import pytest

from highliner.etls.chunk.denmark import dtm_dhm
from highliner.etls.chunk.denmark import main as denmark


def test_denmark_chunk_adapter_uses_dhm_terrain_and_utm32(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(denmark.shared, "precompute", fake)
    denmark.main(["--only", "denmark", "--data-dir", "/tmp/data"])

    assert calls[0]["args"][:2] == ("denmark", "denmark")
    assert calls[0]["crs"] == "EPSG:25832"
    assert calls[0]["dtm_source"] == "denmark_dhm_terrain"
    assert calls[0]["fetch"] is dtm_dhm.fetch


def test_denmark_region_covers_the_official_projected_extent() -> None:
    minx, miny, maxx, maxy = denmark.REGIONS[0].bbox
    assert (minx, miny) == (440_000, 6_040_000)
    assert (maxx, maxy) == (900_000, 6_410_000)


def test_dhm_requires_the_danish_datafordeler_key(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HIGHLINER_DATAFORDELER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="HIGHLINER_DATAFORDELER_API_KEY"):
        dtm_dhm.fetch((500_000, 6_200_000, 501_000, 6_201_000), tmp_path,
                      tmp_path, "EPSG:25832")


def test_dhm_rejects_non_utm32_crs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EPSG:25832"):
        dtm_dhm.fetch((0, 0, 1, 1), tmp_path, tmp_path, "EPSG:4326")
