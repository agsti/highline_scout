from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
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


def _frontend_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def _sitemap() -> str:
    urls = (f"{_CANONICAL_ORIGIN}/", *(f"{_CANONICAL_ORIGIN}{path}"
                                         for path in _METHODOLOGY_PATHS))
    entries = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{entries}</urlset>")


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

    def methodology_shell() -> FileResponse:
        index_html = _frontend_dir() / "index.html"
        if not index_html.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(index_html)

    for path in _METHODOLOGY_PATHS:
        app.add_api_route(path, methodology_shell, include_in_schema=False)
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
