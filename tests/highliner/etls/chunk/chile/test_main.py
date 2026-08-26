import re
from typing import Any

import pytest

from highliner.etls.chunk.chile import main as chile


def test_chile_chunk_adapter_forwards_country_and_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(chile.shared, "precompute", fake)

    chile.main(["--only", "los_rios", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("chile", "los_rios")
    assert calls[0]["workers"] == 5
    assert calls[0]["crs"] == "EPSG:32718"
    assert calls[0]["dtm_source"] == "alos_palsar"

    from highliner.etls.chunk.chile import dtm_alos
    assert calls[0]["fetch"] is dtm_alos.fetch


def test_chile_chunk_adapter_reports_region_progress(
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    def fake(*args: object, **kwargs: object) -> int:
        report = kwargs["report"]
        assert callable(report)
        report(1, 4)
        return 4

    monkeypatch.setattr(chile.shared, "precompute", fake)
    chile.main(["--only", "los_rios", "--data-dir", "/tmp/data"])

    output = capsys.readouterr().out
    assert "[los_rios] starting precompute\n" in output
    assert re.search(
        r"\rchunk 1/4 \(25\.0%\)  elapsed \d+:\d\d:\d\d  "
        r"eta \d+:\d\d:\d\d\n", output)
    assert output.endswith(
        "[los_rios] completed 4 chunks -> /tmp/data/chile/los_rios\n")


def test_chile_chunk_adapter_covers_seventeen_regions_in_their_utm_zone() -> None:
    assert len(chile.REGIONS) == 17
    assert len({region.name for region in chile.REGIONS}) == 17
    for region in chile.REGIONS:
        assert region.crs in ("EPSG:32718", "EPSG:32719")
        assert region.dtm_source == "alos_palsar"
        minx, miny, maxx, maxy = region.bbox
        # Projected meters (UTM), not lon/lat, and snapped to the 1000 m grid.
        assert minx < maxx and miny < maxy
        assert minx % 1000.0 == 0.0
        assert maxy % 1000.0 == 0.0


def test_chile_region_selection_supports_resume_and_explicit_subset() -> None:
    resumed = chile._select_regions("metropolitana", None)
    selected = chile._select_regions(
        None, ["magallanes_sur", "arica_y_parinacota"])

    assert resumed[0].name == "metropolitana"
    assert [region.name for region in selected] == [
        "arica_y_parinacota", "magallanes_sur"]
    assert chile._fmt_hms(3_661.9) == "1:01:01"
    with pytest.raises(SystemExit, match="unknown region"):
        chile._select_regions("missing", None)
