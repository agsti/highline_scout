import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from highliner.core import config
from highliner.core.telemetry import (
    SlowRequestMiddleware,
    api_paths,
    init_posthog,
    init_sentry,
    shutdown_telemetry,
)
from highliner.server.router import anchors, density, regions, restrictions, zones

_CANONICAL_ORIGIN = "https://highlinescout.com"
_METHODOLOGY_PATHS = (
    "/en/how-it-works",
    "/ca/how-it-works",
    "/es/how-it-works",
)
_SOCIAL_CARD = "https://highlinescout.com/social-card.png"
_SOCIAL_CARD_ALT = "Highline Scout logo on a forest-green background"
_METHODOLOGY_METADATA = {
    "/en/how-it-works": (
        "en",
        "How it works | Highline Scout",
        "Find potential highline spots to scout with Highline Scout.",
    ),
    "/ca/how-it-works": (
        "ca",
        "Com funciona | Highline Scout",
        "Descobreix possibles spots de highline per explorar amb Highline Scout.",
    ),
    "/es/how-it-works": (
        "es",
        "Cómo funciona | Highline Scout",
        "Descubre posibles spots de highline para explorar con Highline Scout.",
    ),
}


def _frontend_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def _sitemap() -> str:
    urls = (f"{_CANONICAL_ORIGIN}/", *(f"{_CANONICAL_ORIGIN}{path}"
                                         for path in _METHODOLOGY_PATHS))
    entries = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{entries}</urlset>")


def _methodology_html(index_html: Path, path: str) -> str:
    lang, title, description = _METHODOLOGY_METADATA[path]
    canonical = f"{_CANONICAL_ORIGIN}{path}"
    alternates = "".join(
        f'<link rel="alternate" hreflang="{alternate_lang}" '
        f'href="{_CANONICAL_ORIGIN}/{alternate_lang}/how-it-works">'
        for alternate_lang in ("ca", "es", "en")
    )
    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": "HighlineScout",
        "url": _CANONICAL_ORIGIN + "/",
        "applicationCategory": "TravelApplication",
        "publisher": {"@type": "Organization", "name": "HighlineScout"},
    }, separators=(",", ":"))
    head = (
        "<head>"
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{title}</title>"
        f'<meta name="description" content="{description}">'
        f'<link rel="canonical" href="{canonical}">'
        f"{alternates}"
        '<link rel="alternate" hreflang="x-default" '
        f'href="{_CANONICAL_ORIGIN}/en/how-it-works">'
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:description" content="{description}">'
        f'<meta property="og:url" content="{canonical}">'
        '<meta property="og:type" content="website">'
        f'<meta property="og:image" content="{_SOCIAL_CARD}">'
        '<meta property="og:image:width" content="1200">'
        '<meta property="og:image:height" content="630">'
        f'<meta property="og:image:alt" content="{_SOCIAL_CARD_ALT}">'
        '<meta name="twitter:card" content="summary_large_image">'
        f'<meta name="twitter:title" content="{title}">'
        f'<meta name="twitter:description" content="{description}">'
        f'<script type="application/ld+json">{json_ld}</script>'
        "</head>"
    )
    document = index_html.read_text()
    document = re.sub(r"<html\b[^>]*>", f'<html lang="{lang}">', document,
                      count=1)
    return re.sub(r"<head>.*?</head>", head, document, count=1, flags=re.DOTALL)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    shutdown_telemetry()


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or config.DATA_DIR)

    # Both no-op unless the corresponding credential is configured, so a dev
    # machine sends nothing.
    init_sentry(config.settings)
    init_posthog(config.settings)

    app = FastAPI(title="Highliner Finder", lifespan=_lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    # App-wide state the routers read via highliner.server.router.deps.
    app.state.data_dir = data_dir

    for module in (regions, zones, anchors, density, restrictions):
        app.include_router(module.router)

    def robots() -> PlainTextResponse:
        return PlainTextResponse(
            "User-agent: *\n"
            "Disallow: /regions\n"
            "Disallow: /zones\n"
            "Disallow: /density\n"
            "Disallow: /anchors\n"
            "Disallow: /restrictions\n"
            f"Sitemap: {_CANONICAL_ORIGIN}/sitemap.xml\n"
        )

    def sitemap() -> Response:
        return Response(content=_sitemap(), media_type="application/xml")

    def methodology_shell(path: str) -> HTMLResponse:
        index_html = _frontend_dir() / "index.html"
        if not index_html.is_file():
            raise HTTPException(status_code=404)
        return HTMLResponse(_methodology_html(index_html, path))

    for path in _METHODOLOGY_PATHS:
        app.add_api_route(path, lambda path=path: methodology_shell(path),
                          include_in_schema=False)
    app.add_api_route("/robots.txt", robots, include_in_schema=False)
    app.add_api_route("/sitemap.xml", sitemap, include_in_schema=False)

    # After include_router, so the known-path set covers every API route and
    # collapses everything else (static assets, 404s) to "other".
    app.add_middleware(
        SlowRequestMiddleware,
        threshold_ms=config.settings.slow_request_ms,
        environment=config.settings.environment,
        known_paths=api_paths(app),
    )

    frontend_dir = _frontend_dir()
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True),
                  name="frontend")

    return app


app = create_app()
