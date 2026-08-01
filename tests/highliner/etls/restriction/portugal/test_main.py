import json
from pathlib import Path

import pytest
import requests

from highliner.core.density import layer_mask
from highliner.etls.restriction.portugal import main as portugal


def test_portugal_restriction_specs_have_nonzero_density_bits() -> None:
    assert set(portugal.SPECS) == {"pt_zpe", "pt_zec", "pt_rnap"}
    assert all(layer_mask([layer_id]) != 0 for layer_id in portugal.SPECS)


def test_download_type_follows_wfs_pages(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pages = [[{"id": number} for number in range(portugal._PAGE_SIZE)],
             [{"id": "last"}]]
    starts: list[str] = []

    def fake_get(url: str, params: dict[str, str],
                 timeout: int) -> requests.Response:
        starts.append(params["STARTINDEX"])
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"features": pages.pop(0)}).encode()
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    dest = tmp_path / "zpe.geojson"
    portugal._download_type("zpe", dest)

    assert len(json.loads(dest.read_text())["features"]) == portugal._PAGE_SIZE + 1
    assert starts == ["0", str(portugal._PAGE_SIZE)]
