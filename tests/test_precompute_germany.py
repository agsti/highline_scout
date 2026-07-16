from pathlib import Path
from typing import Any

import pytest


def test_germany_chunk_adapter_forwards_country_and_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk import germany

    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(germany.shared, "precompute", fake)

    germany.main(["--only", "germany", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("germany", "germany")
    assert calls[0]["workers"] == 5
    assert calls[0]["crs"] == "EPSG:25832"
    assert calls[0]["dtm_source"] == "bkg_dgm200"


def test_germany_chunk_adapter_has_a_single_nationwide_metric_region() -> None:
    from highliner.etls.chunk import germany

    assert len(germany.REGIONS) == 1
    region = germany.REGIONS[0]
    assert region.name == "germany"
    assert region.crs == "EPSG:25832"
    assert region.dtm_source == "bkg_dgm200"
    minx, miny, maxx, maxy = region.bbox
    assert 250_000 <= minx < maxx <= 950_000
    assert 5_200_000 <= miny < maxy <= 6_150_000


def test_bkg_dgm200_downloads_geotiff_subset(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    from highliner.etls.chunk import dtm_bkg

    class Response:
        content = b"II*\\x00"
        headers = {"content-type": "image/tiff"}

        def raise_for_status(self) -> None:
            return None

    seen: dict[str, object] = {}

    def fake_get(url: str, *, params: dict[str, str], timeout: int) -> Response:
        seen.update(url=url, params=params, timeout=timeout)
        return Response()

    monkeypatch.setattr(dtm_bkg.requests, "get", fake_get)
    dest = tmp_path / "tile.tif"

    assert dtm_bkg.download_tile((430000, 5300000, 440000, 5310000), dest) == dest
    assert dest.read_bytes() == b"II*\\x00"
    assert seen["params"] == {
        "VERSION": "2.0.1",
        "SERVICE": "WCS",
        "REQUEST": "GetCoverage",
        "COVERAGEID": "dgm200_inspire__EL.GridCoverage",
        "SUBSET": ["E(430000,440000)", "N(5300000,5310000)"],
    }


def test_bkg_dgm200_uses_native_200m_grid() -> None:
    from highliner.etls.chunk import dtm_bkg

    assert dtm_bkg.NATIVE_RES == 200.0


def test_germany_density_adapter_scopes_the_build_to_germany(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.density import germany

    call: dict[str, object] = {}

    def fake(**kwargs: object) -> None:
        call.update(kwargs)

    monkeypatch.setattr(germany.shared, "build_country_density", fake)

    germany.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert call == {"country": "germany", "data_dir": Path("/tmp/data"), "workers": 3}
