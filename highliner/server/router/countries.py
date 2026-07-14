from typing import Any

from fastapi import APIRouter, Request

from highliner.server.router.deps import get_country_index

router = APIRouter()


@router.get("/countries")
def countries(request: Request) -> dict[str, Any]:
    return {"countries": [
        {"id": entry.id, "bounds_lonlat": list(entry.bounds_lonlat),
         "center_lonlat": list(entry.center_lonlat)}
        for entry in get_country_index(request)
    ]}
