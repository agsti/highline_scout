from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from highliner.repositories.dtm import mosaic_bounds_lonlat
from highliner.router.deps import get_data_dir

router = APIRouter()


@router.get("/regions")
def regions(data_dir: Path = Depends(get_data_dir)) -> dict[str, Any]:
    if not data_dir.exists():
        return {"regions": []}
    out = []
    for p in sorted(data_dir.iterdir()):
        if not (p / "anchors.parquet").exists():
            continue
        out.append({"name": p.name,
                    "bounds_lonlat": mosaic_bounds_lonlat(p / "mosaic.tif")})
    return {"regions": out}
