from pathlib import Path
from functools import lru_cache
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from highliner import config, scoring
from highliner.anchors import load_anchors
from highliner.raster import Raster
from highliner.pairing import find_candidates


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or config.DATA_DIR)
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

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


app = create_app()
