"""Fetch Wallonia's CC-BY 1 m LiDAR terrain sheets from SPW bulk downloads."""
import zipfile
from functools import partial
from pathlib import Path

import requests

from highliner.etls.chunk.dtm_core import _download_with_retries

CRS = "EPSG:3812"
Bbox = tuple[float, float, float, float]
BASE_URL = ("https://geoservices.wallonie.be/geotraitement/spwdatadownload/"
            "results/fe13bc84-e371-46ca-9632-8ad4139f1ee5")
_PREFIX = "RELIEF_WALLONIE_MNT_1M_2021_2022_GEOTIFF_3812_PROV_"
SHEETS = {
    "brabant_wallon": f"{_PREFIX}BRABANT_WALLON.zip",
    "hainaut": f"{_PREFIX}HAINAUT.zip",
    "liege": f"{_PREFIX}LIEGE.zip",
    "luxembourg": f"{_PREFIX}LUXEMBOURG.zip",
    "namur": f"{_PREFIX}NAMUR.zip",
}


def _download_sheet(root: Path, name: str) -> Path:
    """Cache and extract one province's GeoTIFF, downloading it once."""
    dest = root / f"{name}.tif"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    response = requests.get(f"{BASE_URL}/{SHEETS[name]}", timeout=900)
    response.raise_for_status()
    archive = root / f"{name}.zip"
    archive.write_bytes(response.content)
    with zipfile.ZipFile(archive) as bundle:
        member = next(item for item in bundle.namelist()
                      if item.lower().endswith((".tif", ".tiff")))
        dest.write_bytes(bundle.read(member))
    archive.unlink(missing_ok=True)
    return dest


def fetch_wallonia_mnt(bbox: Bbox, cache_dir: Path, crs: str) -> list[Path]:
    """Return Wallonia's cached 1 m terrain sheets for a Lambert 2008 chunk."""
    del bbox
    if crs != CRS:
        raise ValueError(f"Wallonia MNT is published in {CRS}, not {crs}")
    root = Path(cache_dir) / "wallonia_mnt_2021_2022"
    root.mkdir(parents=True, exist_ok=True)
    return [_download_with_retries(partial(_download_sheet, root, name))
            for name in SHEETS]


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source='wallonia_mnt_2021_2022'``."""
    del tiles_dir
    if cache_dir is None:
        raise ValueError("wallonia_mnt_2021_2022 source requires cache_dir")
    return fetch_wallonia_mnt(bbox, cache_dir, crs)
