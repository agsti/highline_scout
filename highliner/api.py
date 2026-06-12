import re
from pathlib import Path
from functools import lru_cache
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from highliner import config, ingest, restrictions, zones as zones_mod
from highliner.anchors import load_anchors, to_geojson as anchors_to_geojson
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


def _bbox_utm(bbox, bbox_lonlat):
    """Return (minx, miny, maxx, maxy) in UTM from either a UTM bbox string
    or a lon/lat bbox string. Raises HTTPException(400) if neither given."""
    from highliner import geo
    if bbox_lonlat:
        w, s, e, n = (float(v) for v in bbox_lonlat.split(","))
        minx, miny = geo.to_utm(w, s)
        maxx, maxy = geo.to_utm(e, n)
        return minx, miny, maxx, maxy
    if bbox:
        return tuple(float(v) for v in bbox.split(","))
    raise HTTPException(400, "provide bbox or bbox_lonlat")


def _bbox_lonlat(bbox, bbox_lonlat):
    """Return (w, s, e, n) in lon/lat from a lon/lat bbox string, or by
    converting a UTM bbox string's corners. Raises 400 if neither given."""
    if bbox_lonlat:
        return tuple(float(v) for v in bbox_lonlat.split(","))
    if bbox:
        from highliner import geo
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
        w, s = geo.to_lonlat(minx, miny)
        e, n = geo.to_lonlat(maxx, maxy)
        return w, s, e, n
    raise HTTPException(400, "provide bbox or bbox_lonlat")


def _mosaic_bounds_lonlat(mosaic_path):
    """Lon/lat extent [w, s, e, n] of a region's mosaic, or None if missing.
    Reads only raster metadata (no pixel data) and converts the four UTM
    corners, taking the min/max so the box stays axis-aligned in lon/lat."""
    from highliner import geo
    if not mosaic_path.exists():
        return None
    import rasterio
    with rasterio.open(mosaic_path) as ds:
        b = ds.bounds
    corners = [geo.to_lonlat(x, y)
               for x in (b.left, b.right) for y in (b.bottom, b.top)]
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    return [min(lons), min(lats), max(lons), max(lats)]


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
        out = []
        for p in sorted(data_dir.iterdir()):
            if not (p / "anchors.parquet").exists():
                continue
            out.append({"name": p.name,
                        "bounds_lonlat": _mosaic_bounds_lonlat(p / "mosaic.tif")})
        return {"regions": out}

    @app.get("/zones")
    def zones(
        region: str,
        bbox: str | None = None,
        bbox_lonlat: str | None = None,
        max_len: float = config.DEFAULT_MAX_LEN_M,
        min_len: float = config.DEFAULT_MIN_LEN_M,
        min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
        max_dh: float = config.DEFAULT_MAX_DH_M,
        cluster_dist: float = config.CLUSTER_DIST_M,
    ):
        anchors, raster = _region(region)
        minx, miny, maxx, maxy = _bbox_utm(bbox, bbox_lonlat)
        in_view = [a for a in anchors
                   if minx <= a.x <= maxx and miny <= a.y <= maxy]
        if len(in_view) > config.MAX_ANCHORS_IN_VIEW:
            raise HTTPException(413, "too many anchors in view; zoom in")
        cands = find_candidates(in_view, raster, max_len, min_len,
                                min_exposure, max_dh)
        return zones_mod.to_geojson(zones_mod.build_zones(cands, cluster_dist))

    @app.get("/anchors")
    def anchors(
        region: str,
        bbox: str | None = None,
        bbox_lonlat: str | None = None,
    ):
        anchor_list, _raster = _region(region)
        minx, miny, maxx, maxy = _bbox_utm(bbox, bbox_lonlat)
        in_view = [a for a in anchor_list
                   if minx <= a.x <= maxx and miny <= a.y <= maxy]
        if len(in_view) > config.MAX_ANCHORS_IN_VIEW:
            raise HTTPException(413, "too many anchors in view; zoom in")
        return anchors_to_geojson(in_view)

    @app.get("/restrictions/layers")
    def restriction_layers():
        return {"layers": restrictions.layer_meta()}

    @app.get("/restrictions")
    def restrictions_in_view(
        bbox: str | None = None,
        bbox_lonlat: str | None = None,
        layers: str | None = None,
    ):
        box = _bbox_lonlat(bbox, bbox_lonlat)
        ids = ([x for x in layers.split(",") if x in restrictions.LAYERS]
               if layers else list(restrictions.LAYERS))
        rdir = data_dir / "restrictions"
        feats: list[dict] = []
        for layer_id in ids:
            path = rdir / f"{layer_id}.parquet"
            if not path.exists():
                continue
            gdf = restrictions.load_layer(str(path))
            feats.extend(restrictions.clip_to_features(layer_id, gdf, box))
            if len(feats) > config.MAX_RESTRICTION_FEATURES:
                raise HTTPException(413, "too many areas in view; zoom in")
        return {"type": "FeatureCollection", "features": feats}

    @app.post("/analyze")
    def analyze(req: AnalyzeRequest):
        bbox = _bbox_utm(req.bbox, req.bbox_lonlat)

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
