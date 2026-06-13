from pathlib import Path

from fastapi import APIRouter, Depends

from highliner.core import geo
from highliner.router.deps import get_data_dir

router = APIRouter()


def _mosaic_bounds_lonlat(mosaic_path):
    """Lon/lat extent [w, s, e, n] of a region's mosaic, or None if missing.
    Reads only raster metadata (no pixel data) and converts the four UTM
    corners, taking the min/max so the box stays axis-aligned in lon/lat."""
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


@router.get("/regions")
def regions(data_dir: Path = Depends(get_data_dir)):
    if not data_dir.exists():
        return {"regions": []}
    out = []
    for p in sorted(data_dir.iterdir()):
        if not (p / "anchors.parquet").exists():
            continue
        out.append({"name": p.name,
                    "bounds_lonlat": _mosaic_bounds_lonlat(p / "mosaic.tif")})
    return {"regions": out}
