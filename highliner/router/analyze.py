import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from highliner.core import config
from highliner.repositories import dtm
from highliner.tasks.analyze import analyze_task
from highliner.router.deps import parse_bbox_utm

router = APIRouter()


class AnalyzeRequest(BaseModel):
    name: str | None = None
    bbox_lonlat: str | None = None
    bbox: str | None = None


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "region"


def _unique_region(data_dir: Path, slug: str) -> str:
    region = slug
    i = 2
    while (data_dir / region).exists():
        region = f"{slug}-{i}"
        i += 1
    return region


@router.post("/analyze")
def analyze(req: AnalyzeRequest, request: Request) -> dict[str, Any]:
    data_dir = request.app.state.data_dir
    store = request.app.state.jobstore
    bbox = parse_bbox_utm(req.bbox, req.bbox_lonlat)

    tiles = dtm.estimate_tiles(bbox)
    if tiles > config.MAX_ANALYZE_TILES:
        raise HTTPException(
            400, f"area too large ({tiles} tiles > "
                 f"{config.MAX_ANALYZE_TILES}); zoom in")

    name = (req.name or "").strip() or "region"
    region = _unique_region(data_dir, _slugify(name))
    job_id = store.create(name=name, region=region)
    analyze_task(bbox, region, str(data_dir), job_id)
    return {"job_id": job_id, "region": region}
