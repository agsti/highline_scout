from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


app = create_app()
