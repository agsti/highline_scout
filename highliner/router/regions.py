from typing import Any

from fastapi import APIRouter, Request

from highliner.router.deps import get_region_index

router = APIRouter()


@router.get("/regions")
def regions(request: Request) -> dict[str, Any]:
    out = [{"name": e.name, "bounds_lonlat": list(e.lonlat_bounds)}
           for e in get_region_index(request)]
    return {"regions": out}
