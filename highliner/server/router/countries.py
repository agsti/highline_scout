from typing import Any

from fastapi import APIRouter, Request

from highliner.server.router.deps import get_country_index

router = APIRouter()


@router.get("/countries")
def countries(request: Request) -> dict[str, Any]:
    return {"countries": [
        {
            "id": entry.id,
            "bounds_lonlat": list(entry.bounds_lonlat),
            **({"country_code": entry.country_code}
               if entry.country_code is not None else {}),
        }
        for entry in get_country_index(request)
    ]}
