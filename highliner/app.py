from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from highliner.core import config
from highliner.core.telemetry import (
    SlowRequestMiddleware,
    api_paths,
    init_posthog,
    init_sentry,
    shutdown_telemetry,
)
from highliner.router import anchors, density, regions, restrictions, zones


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

    # App-wide state the routers read via highliner.router.deps.
    app.state.data_dir = data_dir

    for module in (regions, zones, anchors, density, restrictions):
        app.include_router(module.router)

    # After include_router, so the known-path set covers every API route and
    # collapses everything else (static assets, 404s) to "other".
    app.add_middleware(
        SlowRequestMiddleware,
        threshold_ms=config.settings.slow_request_ms,
        environment=config.settings.environment,
        known_paths=api_paths(app),
    )

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True),
                  name="frontend")

    return app


app = create_app()
