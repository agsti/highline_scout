from pathlib import Path
import requests
from highliner import config

# ICGC WCS coverage for the 2m DTM. Adjust coverage id if ICGC changes it.
ICGC_WCS = "https://geoserveis.icgc.cat/servei/catalunya/model-elevacions/wcs"
COVERAGE_ID = "het2m"  # 2m bare-earth elevation model


def _download_dtm(bbox, dest: Path) -> Path:
    minx, miny, maxx, maxy = bbox
    params = {
        "service": "WCS",
        "version": "2.0.1",
        "request": "GetCoverage",
        "coverageId": COVERAGE_ID,
        "format": "image/tiff",
        "subset": [f"E({minx},{maxx})", f"N({miny},{maxy})"],
    }
    r = requests.get(ICGC_WCS, params=params, timeout=120)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def fetch_dtm(bbox, region: str, data_dir: Path | None = None) -> Path:
    data_dir = Path(data_dir or config.DATA_DIR)
    region_dir = data_dir / region
    region_dir.mkdir(parents=True, exist_ok=True)
    minx, miny, maxx, maxy = (int(round(v)) for v in bbox)
    dest = region_dir / f"dtm_{minx}_{miny}_{maxx}_{maxy}.tif"
    if dest.exists():
        return dest
    return _download_dtm(bbox, dest)
