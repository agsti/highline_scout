from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from highliner.server import app as app_module


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    (tmp_path / "index.html").write_text("<html>shell</html>")
    monkeypatch.setattr(app_module, "_frontend_dir", lambda: tmp_path,
                        raising=False)
    return TestClient(app_module.create_app(data_dir=tmp_path))


def test_sitemap_lists_only_public_urls(client: TestClient) -> None:
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Sitemap: https://highlinescout.com/sitemap.xml" in robots.text
    for prefix in ("/regions", "/zones", "/density", "/anchors",
                   "/restrictions"):
        assert f"Disallow: {prefix}" in robots.text

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert sitemap.headers["content-type"].startswith("application/xml")
    for path in ("", "/en/how-it-works", "/ca/how-it-works",
                 "/es/how-it-works"):
        assert f"https://highlinescout.com{path}" in sitemap.text
    assert "/zones" not in sitemap.text


@pytest.mark.parametrize("path", ["/en/how-it-works", "/ca/how-it-works",
                                  "/es/how-it-works"])
def test_methodology_routes_return_built_shell(client: TestClient,
                                                path: str) -> None:
    assert client.get(path).text == "<html>shell</html>"


def test_unknown_path_remains_not_found(client: TestClient) -> None:
    assert client.get("/unknown").status_code == 404


def test_methodology_route_is_not_found_without_built_shell(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_frontend_dir", lambda: tmp_path)
    client = TestClient(app_module.create_app(data_dir=tmp_path),
                        raise_server_exceptions=False)

    assert client.get("/en/how-it-works").status_code == 404
