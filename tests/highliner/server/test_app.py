from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from highliner.core import config
from highliner.server import app as app_module
from highliner.server.app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    (tmp_path / "index.html").write_text(
        "<!doctype html><html lang=\"en\"><head><title>Shell</title>"
        "<link rel=\"stylesheet\" href=\"/assets/app.css\">"
        "<script type=\"module\" src=\"/assets/app.js\"></script></head>"
        "<body><div id=\"root\"></div></body></html>"
    )
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


@pytest.mark.parametrize(
    ("path", "lang", "title", "description"),
    [
        ("/en/how-it-works", "en", "How it works | Highline Scout",
         "Find potential highline spots to scout with Highline Scout."),
        ("/ca/how-it-works", "ca", "Com funciona | Highline Scout",
         "Descobreix possibles spots de highline per explorar amb Highline Scout."),
        ("/es/how-it-works", "es", "Cómo funciona | Highline Scout",
         "Descubre posibles spots de highline para explorar con Highline Scout."),
    ],
)
def test_methodology_routes_render_localized_metadata_for_crawlers(
        client: TestClient, path: str, lang: str, title: str,
        description: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert f'<html lang="{lang}">' in response.text
    assert '<link rel="stylesheet" href="/assets/app.css">' in response.text
    assert '<script type="module" src="/assets/app.js"></script>' in response.text
    assert f"<title>{title}</title>" in response.text
    assert f'<meta name="description" content="{description}">' in response.text
    assert (
        f'<link rel="canonical" href="https://highlinescout.com{path}">'
        in response.text
    )
    assert f'<meta property="og:title" content="{title}">' in response.text
    assert (
        f'<meta property="og:description" content="{description}">'
        in response.text
    )
    assert (
        f'<meta property="og:url" content="https://highlinescout.com{path}">'
        in response.text
    )
    for alternate_lang in ("ca", "es", "en"):
        assert (
            f'<link rel="alternate" hreflang="{alternate_lang}" '
            f'href="https://highlinescout.com/{alternate_lang}/how-it-works">'
            in response.text
        )
    assert (
        '<link rel="alternate" hreflang="x-default" '
        'href="https://highlinescout.com/en/how-it-works">' in response.text
    )
    assert (
        '<meta property="og:image" '
        'content="https://highlinescout.com/social-card.png">' in response.text
    )
    assert '<meta property="og:image:width" content="1200">' in response.text
    assert '<meta property="og:image:height" content="630">' in response.text
    assert (
        '<meta property="og:image:alt" '
        'content="Highline Scout logo on a forest-green background">' in response.text
    )
    assert '<meta name="twitter:card" content="summary_large_image">' in response.text
    assert '"@type":"WebApplication"' in response.text
    assert "confirmed-riggable" not in response.text


@pytest.mark.parametrize("query_path", ("/es/how-it-works", "/not-a-route"))
def test_methodology_metadata_uses_the_bound_route_not_query_params(
        client: TestClient, query_path: str) -> None:
    response = client.get(f"/en/how-it-works?path={query_path}")

    assert response.status_code == 200
    assert "<title>How it works | Highline Scout</title>" in response.text


def test_unknown_path_remains_not_found(client: TestClient) -> None:
    assert client.get("/unknown").status_code == 404


def test_static_index_has_english_metadata_for_non_js_crawlers() -> None:
    index_html = (Path(__file__).parents[3] / "frontend" / "index.html").read_text()

    assert '<html lang="en">' in index_html
    assert (
        "<title>HighlineScout | The smarter way to scout your next line</title>"
        in index_html
    )
    assert '<link rel="canonical" href="https://highlinescout.com/"' in index_html
    assert (
        '<meta property="og:title" '
        'content="HighlineScout | The smarter way to scout your next line"'
        in index_html
    )
    assert (
        '<meta property="og:image" '
        'content="https://highlinescout.com/social-card.png"' in index_html
    )
    assert '<meta property="og:image:width" content="1200"' in index_html
    assert '<meta property="og:image:height" content="630"' in index_html
    assert (
        '<meta property="og:image:alt" '
        'content="Highline Scout logo on a forest-green background"' in index_html
    )
    assert '<meta name="twitter:card" content="summary_large_image"' in index_html
    assert '"@type":"WebApplication"' in index_html


def test_methodology_route_is_not_found_without_built_shell(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_frontend_dir", lambda: tmp_path)
    client = TestClient(app_module.create_app(data_dir=tmp_path),
                        raise_server_exceptions=False)

    assert client.get("/en/how-it-works").status_code == 404


def test_candidates_route_removed(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/candidates", params={"region": "test", "bbox": "0,0,300,300"})
    assert r.status_code == 404


def test_app_installs_slow_request_middleware() -> None:
    from typing import cast

    from highliner.core.telemetry import SlowRequestMiddleware

    app = create_app()

    # Starlette types .cls as a middleware factory, so compare through object.
    installed = [cast(object, m.cls) for m in app.user_middleware]
    assert SlowRequestMiddleware in installed


def test_app_compresses_eligible_responses() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.json()["openapi"] == "3.1.0"


def test_app_sends_nothing_without_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default (unconfigured) app must not attempt any telemetry IO.

    Threshold is forced to 0 so every request crosses it — if the disabled-state
    guard were missing, this would call into an unarmed PostHog client.
    """
    import posthog

    monkeypatch.setattr(config.settings, "slow_request_ms", 0.0)
    calls: list[object] = []
    monkeypatch.setattr(posthog, "capture", lambda **kwargs: calls.append(kwargs))

    client = TestClient(create_app(tmp_path))
    client.get("/regions")

    assert calls == []
