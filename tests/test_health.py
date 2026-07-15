from pathlib import Path

from fastapi.testclient import TestClient
from highliner.server.app import create_app


def test_healthz_is_a_bare_liveness_probe(tmp_path: Path) -> None:
    """200 with no data present: the probe must not depend on partitions, so a
    transient data issue can't wedge the reverse proxy / monitor into restarts."""
    client = TestClient(create_app(tmp_path))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
