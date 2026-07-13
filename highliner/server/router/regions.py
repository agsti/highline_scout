from typing import Any

from fastapi import APIRouter, Request

from highliner.core import config
from highliner.server.router.deps import get_region_index, regions_in_country

router = APIRouter()


@router.get("/regions")
def regions(request: Request,
            country: str = config.DEFAULT_COUNTRY) -> dict[str, Any]:
    index = regions_in_country(get_region_index(request), country)
    out = [{"name": e.name, "country": e.country,
            "bounds_lonlat": list(e.lonlat_bounds)}
           for e in index]
    return {"regions": out}
