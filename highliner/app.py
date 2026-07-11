from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from highliner.core import config
from highliner.router import (anchors, density, regions, restrictions, zones)



def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or config.DATA_DIR)
    app = FastAPI(title="Highliner Finder")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    # App-wide state the routers read via highliner.router.deps.
    app.state.data_dir = data_dir

    for module in (regions, zones, anchors, density, restrictions):
        app.include_router(module.router)

    frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True),
                  name="frontend")

    return app


app = create_app()
