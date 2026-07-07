from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from highliner.core import geo
from highliner.repositories import chunked_store
from highliner.router.deps import get_data_dir

router = APIRouter()


def _bounds_from_grid(region_dir: Path) -> list[float]:
    grid = chunked_store.read_grid(region_dir)
    minx, miny, maxx, maxy = grid.bbox
    corners = [geo.to_lonlat(x, y) for x in (minx, maxx) for y in (miny, maxy)]
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    return [min(lons), min(lats), max(lons), max(lats)]


@router.get("/regions")
def regions(data_dir: Path = Depends(get_data_dir)) -> dict[str, Any]:
    if not data_dir.exists():
        return {"regions": []}
    out: list[dict[str, Any]] = []
    for p in sorted(data_dir.iterdir()):
        if (p / "grid.json").exists():
            out.append({"name": p.name, "bounds_lonlat": _bounds_from_grid(p)})
    return {"regions": out}
