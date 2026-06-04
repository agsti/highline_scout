import re
from pathlib import Path
from functools import lru_cache
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from highliner import config, scoring, ingest
from highliner.anchors import load_anchors
from highliner.raster import Raster
from highliner.pairing import find_candidates
from highliner.jobstore import JobStore
from highliner.tasks import analyze_task, huey
from huey.consumer import Consumer


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "region"


def _unique_region(data_dir, slug: str) -> str:
    region = slug
    i = 2
    while (data_dir / region).exists():
        region = f"{slug}-{i}"
        i += 1
    return region


class AnalyzeRequest(BaseModel):
    name: str | None = None
    bbox_lonlat: str | None = None
    bbox: str | None = None


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or config.DATA_DIR)
    store = JobStore(data_dir / "jobs.db")
    app = FastAPI(title="Highliner Finder")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    @lru_cache(maxsize=8)
    def _region(region: str):
        rdir = data_dir / region
        apath = rdir / "anchors.parquet"
        mpath = rdir / "mosaic.tif"
        if not apath.exists() or not mpath.exists():
            raise HTTPException(404, f"region '{region}' not found")
        return load_anchors(apath), Raster.open(mpath)

    @app.get("/regions")
    def regions():
        if not data_dir.exists():
            return {"regions": []}
        names = [p.name for p in data_dir.iterdir()
                 if (p / "anchors.parquet").exists()]
        return {"regions": sorted(names)}

    @app.get("/candidates")
    def candidates(
        region: str,
        bbox: str | None = None,
        bbox_lonlat: str | None = None,
        max_len: float = config.DEFAULT_MAX_LEN_M,
        min_len: float = config.DEFAULT_MIN_LEN_M,
        min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
        max_dh: float = config.DEFAULT_MAX_DH_M,
    ):
        from highliner import geo
        anchors, raster = _region(region)
        if bbox_lonlat:
            w, s, e, n = (float(v) for v in bbox_lonlat.split(","))
            minx, miny = geo.to_utm(w, s)
            maxx, maxy = geo.to_utm(e, n)
        elif bbox:
            minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
        else:
            raise HTTPException(400, "provide bbox or bbox_lonlat")
        in_view = [a for a in anchors
                   if minx <= a.x <= maxx and miny <= a.y <= maxy]
        if len(in_view) > 20000:
            raise HTTPException(413, "too many anchors in view; zoom in")
        cands = find_candidates(in_view, raster, max_len, min_len,
                                min_exposure, max_dh)
        cands = sorted(cands, key=scoring.score,
                       reverse=True)[:config.MAX_CANDIDATES]
        return scoring.to_geojson(cands)

    @app.post("/analyze")
    def analyze(req: AnalyzeRequest):
        from highliner import geo
        if req.bbox_lonlat:
            w, s, e, n = (float(v) for v in req.bbox_lonlat.split(","))
            minx, miny = geo.to_utm(w, s)
            maxx, maxy = geo.to_utm(e, n)
        elif req.bbox:
            minx, miny, maxx, maxy = (float(v) for v in req.bbox.split(","))
        else:
            raise HTTPException(400, "provide bbox or bbox_lonlat")
        bbox = (minx, miny, maxx, maxy)

        tiles = ingest.estimate_tiles(bbox)
        if tiles > config.MAX_ANALYZE_TILES:
            raise HTTPException(
                400, f"area too large ({tiles} tiles > "
                     f"{config.MAX_ANALYZE_TILES}); zoom in")

        name = (req.name or "").strip() or "region"
        region = _unique_region(data_dir, _slugify(name))
        job_id = store.create(name=name, region=region)
        analyze_task(bbox, region, str(data_dir), job_id)
        return {"job_id": job_id, "region": region}

    @app.get("/jobs")
    def jobs():
        return {"jobs": store.list()}

    @app.get("/jobs/{job_id}")
    def job(job_id: str):
        j = store.get(job_id)
        if j is None:
            raise HTTPException(404, "job not found")
        return j

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
