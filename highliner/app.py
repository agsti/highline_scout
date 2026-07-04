from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from highliner.core import config
from highliner.router import (anchors, density, regions, restrictions, zones)


class _NoCacheStaticFiles(StaticFiles):
    """Serve the web/ assets with forced revalidation.

    There's no build step, so assets keep stable unversioned names (app.js,
    i18n.js, ...). With the default heuristic browser cache a returning visitor
    can pair a stale cached app.js with a freshly deployed index.html and throw
    (e.g. `restrictionText is not defined`). `Cache-Control: no-cache` lets the
    browser cache but revalidate via ETag on every load — a cheap 304 when a
    file is unchanged, fresh bytes the moment a deploy changes it.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or config.DATA_DIR)
    app = FastAPI(title="Highliner Finder")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    # App-wide state the routers read via highliner.router.deps.
    app.state.data_dir = data_dir

    for module in (regions, zones, anchors, density, restrictions):
        app.include_router(module.router)

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        app.mount("/", _NoCacheStaticFiles(directory=web_dir, html=True), name="web")

    return app


app = create_app()
