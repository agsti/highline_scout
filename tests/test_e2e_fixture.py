from pathlib import Path

from fastapi.testclient import TestClient
from highliner.server.app import create_app

FIXTURE_DATA = Path("tests/fixtures/e2e-data")
VIEW = "1.82,41.58,1.84,41.60"


def test_e2e_fixture_serves_density_and_filterable_zones() -> None:
    client = TestClient(create_app(FIXTURE_DATA))

    density = client.get(
        "/density",
        params={"z": 14, "bbox_lonlat": VIEW, "country": "spain"},
    )
    zones = client.get(
        "/zones",
        params={"bbox_lonlat": VIEW, "country": "spain"},
    )
    filtered = client.get(
        "/zones",
        params={
            "bbox_lonlat": VIEW,
            "country": "spain",
            "min_exposure": 70,
        },
    )

    assert density.status_code == zones.status_code == filtered.status_code == 200
    assert len(density.json()["features"]) == 1
    assert len(zones.json()["features"]) == 2
    assert len(filtered.json()["features"]) == 1
