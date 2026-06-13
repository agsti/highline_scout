from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from huey.consumer import Consumer

from highliner.core import config
from highliner.repositories.jobs import JobStore
from highliner.tasks.analyze import huey
from highliner.router import (analyze, anchors, jobs, regions, restrictions,
                              zones)


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or config.DATA_DIR)
    app = FastAPI(title="Highliner Finder")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    # App-wide state the routers read via highliner.router.deps.
    app.state.data_dir = data_dir
    app.state.jobstore = JobStore(data_dir / "jobs.db")

    for module in (regions, zones, anchors, restrictions, jobs, analyze):
        app.include_router(module.router)

    @app.on_event("startup")
    def _start_consumer():
        app.state.huey_consumer = None
        app.state.huey_consumer_stopped = False
        if not huey.immediate:
            consumer = Consumer(huey, workers=1, worker_type="thread")
            # Embedded consumer: the app process owns signal handling, and
            # startup may run off the main thread (e.g. TestClient), where
            # signal.signal() raises. Skip huey's own handler registration.
            consumer._set_signal_handlers = lambda: None
            consumer.start()  # spawns worker + scheduler threads only
            app.state.huey_consumer = consumer

    @app.on_event("shutdown")
    def _stop_consumer():
        consumer = getattr(app.state, "huey_consumer", None)
        if consumer is not None:
            consumer.stop()
        app.state.huey_consumer_stopped = True

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


app = create_app()
