from pathlib import Path

from fastapi.testclient import TestClient

from highliner.server.app import create_app
from tests.helpers import facing_pair as _facing_pair
from tests.helpers import gap_region as _gap_region
from tests.helpers import write_region as _write_region


def test_regions_lists_region(tmp_path: Path) -> None:
    _gap_region(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    found = [r for r in client.get("/regions").json()["regions"] if r["name"] == "test"]
    assert len(found) == 1
    b = found[0]["bounds_lonlat"]
    assert b is not None and len(b) == 4
    assert b[0] < b[2] and b[1] < b[3]


def test_regions_exposes_country_and_filters(tmp_path: Path) -> None:
    cx1, cy1, a1, b1, c1 = _facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx1 - 200, cy1 - 200, cx1 + 200, cy1 + 200),
                  [a1, b1], [c1])                              # spain (default)
    cx2, cy2, a2, b2, c2 = _facing_pair(1.95, 41.60)
    _write_region(tmp_path, "two", (cx2 - 200, cy2 - 200, cx2 + 200, cy2 + 200),
                  [a2, b2], [c2], country="france")
    client = TestClient(create_app(data_dir=tmp_path))

    default = client.get("/regions").json()["regions"]   # default country: spain
    assert [r["name"] for r in default] == ["one"]
    assert default[0]["country"] == "spain"

    fr = client.get("/regions", params={"country": "france"}).json()["regions"]
    assert [(r["name"], r["country"]) for r in fr] == [("two", "france")]
