from typing import Any

import pytest

from highliner.etls.chunk.finland import main as finland


def test_finland_chunk_adapter_forwards_nls_configuration(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(finland.shared, "precompute", fake)

    finland.main(["--only", "finland", "--data-dir", "/tmp/data", "--workers", "2"])

    assert calls[0]["args"][:2] == ("finland", "finland")
    assert calls[0]["crs"] == "EPSG:3067"
    assert calls[0]["dtm_source"] == "nls_korkeusmalli_2m"
    assert calls[0]["workers"] == 2


def test_finland_region_selection_validates_values() -> None:
    assert finland._select_regions("finland", None) == finland.REGIONS
    assert finland._select_regions(None, ["elsewhere"]) == ()
    with pytest.raises(SystemExit, match="unknown region"):
        finland._select_regions("missing", None)
