"""Fetch RGE ALTI 5 m department sheets covering France (IGN Géoplateforme).

RGE ALTI (IGN, Licence Ouverte 2.0) is distributed by the Géoplateforme
download service as one 7z archive per department, each containing 5 km ASC
dalles (1000x1000 cells at 5 m) in Lambert-93 (EPSG:2154 — Corsica shares the
horizontal CRS; only its vertical datum differs). Sea and out-of-department
cells are plain ``NODATA_value -99999``; there is no separate sea sentinel.

Bulk-sheet pattern like Spain's CNIG source: each department archive is
downloaded once into the persistent country cache, its ASC dalles converted
to deflate GeoTIFFs (a fraction of the text size, with CRS and nodata stamped
so ``merge`` masks the sea), and every chunk afterwards is a local read of
the dalles intersecting its bbox. Which departments a chunk touches is
resolved through the ADMIN EXPRESS WFS and cached, mirroring the CNIG
sheet-index cache.
"""
import fcntl as fcntl
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

import py7zr
import rasterio
import requests

DOWNLOAD_BASE = "https://data.geopf.fr/telechargement"
WFS_URL = "https://data.geopf.fr/wfs/ows"
HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}
CRS = "EPSG:2154"
NODATA = -99999.0
TILE_M = 5000.0               # dalle side: 1000 px at 5 m
# Dalle grids are registered on cell centers, so corners sit half a cell
# (2.5 m) off the round-kilometer coordinate the filename encodes.
_HALF_CELL_M = 2.5
_TIMEOUT_S = 300
_RETRY_ATTEMPTS = 6           # archives are 50-500 MB streams; resume on drop
_RETRY_BASE_S = 3.0
_CATALOG_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_WFS_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_ARCHIVE_RE = re.compile(r"RGEALTI_2-0_5M_ASC_LAMB93-[A-Z0-9]+_(D\w{3})_")
_DALLE_RE = re.compile(r"_(\d{4})_(\d{4})_")

Bbox = tuple[float, float, float, float]


def fetch_rgealti_tiles(bbox: Bbox, cache_root: Path, crs: str) -> list[Path]:
    """Return cached dalle GeoTIFFs covering ``bbox``, downloading and
    extracting the owning department archives on first use."""
    if crs != CRS:
        raise RuntimeError(f"RGE ALTI 5M is published in {CRS}, not {crs}")
    cache_root = Path(cache_root)
    session = _session()
    catalog = _cached_catalog(session, cache_root)
    out: list[Path] = []
    for code in _cached_departments(session, bbox,
                                    cache_root / "rgealti_dep_index"):
        zone = _zone(code)
        archive = catalog.get(zone)
        if archive is None:
            raise RuntimeError(f"no RGE ALTI 5M archive for department {zone}")
        out.extend(_select_dalles(
            _ensure_department(session, archive, zone, cache_root), bbox))
    return out


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _zone(code_insee: str) -> str:
    """Map an INSEE department code to its catalog zone (01 -> D001)."""
    return "D" + code_insee.rjust(3, "0")


def _wfs_request(session: requests.Session,
                 params: dict[str, str]) -> requests.Response:
    """Fetch one WFS response, retrying throttles and transient failures."""
    for attempt in range(_RETRY_ATTEMPTS):
        last = attempt == _RETRY_ATTEMPTS - 1
        try:
            response = session.get(WFS_URL, params=params, timeout=120)
        except requests.RequestException as exc:
            if last:
                raise
            retry_response = exc.response
            if retry_response is not None:
                retry_response.close()
            time.sleep(_catalog_retry_delay(attempt, retry_response))
            continue
        if response.status_code in _WFS_RETRY_STATUS and not last:
            response.close()
            time.sleep(_catalog_retry_delay(attempt, response))
            continue
        return response
    raise RuntimeError("unreachable")


def _departments(session: requests.Session, bbox: Bbox) -> list[str]:
    """INSEE codes of the departments intersecting ``bbox`` (EPSG:2154)."""
    minx, miny, maxx, maxy = bbox
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": "ADMINEXPRESS-COG-CARTO.LATEST:departement",
        "SRSNAME": "urn:ogc:def:crs:EPSG::2154",
        "BBOX": f"{minx},{miny},{maxx},{maxy},urn:ogc:def:crs:EPSG::2154",
        "outputFormat": "application/json",
        "PROPERTYNAME": "code_insee",
        "COUNT": "50",
    }
    r = _wfs_request(session, params)
    r.raise_for_status()
    return sorted({feature["properties"]["code_insee"]
                   for feature in r.json()["features"]})


def _department_cache_key(bbox: Bbox) -> str:
    return hashlib.sha1(json.dumps(list(bbox)).encode()).hexdigest()


def _cached_departments(session: requests.Session, bbox: Bbox,
                        cache_dir: Path) -> list[str]:
    """Resolve ``bbox`` once across workers and cache its department codes."""
    key = _department_cache_key(bbox)
    path = cache_dir / f"{key}.json"
    if path.exists():
        return list(json.loads(path.read_text()))
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".json.lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            return list(json.loads(path.read_text()))
        codes = _departments(session, bbox)
        tmp = path.with_suffix(f".json.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(codes))
        tmp.replace(path)
    return codes


def _catalog_retry_delay(attempt: int,
                         response: requests.Response | None = None) -> float:
    """Back off exponentially, honoring a longer catalog Retry-After."""
    if response is None:
        return _RETRY_BASE_S * 2.0 ** attempt
    try:
        retry_after = float(response.headers.get("Retry-After", 0) or 0)
    except ValueError:
        retry_after = 0.0
    return max(retry_after, _RETRY_BASE_S * 2.0 ** attempt)


def _catalog_page(session: requests.Session, page: int) -> requests.Response:
    """Fetch one catalog page, retrying provider throttles and 5xx errors."""
    for attempt in range(_RETRY_ATTEMPTS):
        response = session.get(f"{DOWNLOAD_BASE}/resource/RGEALTI",
                               params={"page": str(page)}, timeout=60)
        if response.status_code not in _CATALOG_RETRY_STATUS \
                or attempt == _RETRY_ATTEMPTS - 1:
            response.raise_for_status()
            return response
        response.close()
        time.sleep(_catalog_retry_delay(attempt, response))
    raise RuntimeError("unreachable")


def _crawl_catalog(session: requests.Session) -> dict[str, str]:
    """Map department zones (D001) to 5M LAMB93 archive names, crawling the
    Atom feed of the RGEALTI download resource page by page."""
    out: dict[str, str] = {}
    page = 1
    while True:
        if page > 1:
            time.sleep(1.0)
        r = _catalog_page(session, page)
        for title in re.findall(r"<title>(RGEALTI_[^<]+)</title>", r.text):
            match = _ARCHIVE_RE.match(title)
            if match:
                out[match.group(1)] = title
        pagecount = re.search(r'pagecount="(\d+)"', r.text)
        if pagecount is None or page >= int(pagecount.group(1)):
            return out
        page += 1


def _cached_catalog(session: requests.Session,
                    cache_root: Path) -> dict[str, str]:
    """Load the zone -> archive catalog, crawling it once under a flock so
    concurrent chunk workers share a single crawl."""
    path = cache_root / "rgealti_catalog.json"
    if path.exists():
        return dict(json.loads(path.read_text()))
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".json.lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not path.exists():
            catalog = _crawl_catalog(session)
            if not catalog:
                raise RuntimeError("RGEALTI catalog crawl found no 5M archives")
            tmp = path.with_suffix(f".json.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(catalog))
            tmp.replace(path)
    return dict(json.loads(path.read_text()))


def _download_archive(session: requests.Session, archive: str,
                      dest: Path) -> None:
    """Stream one department 7z to ``dest``, resuming dropped streams."""
    url = f"{DOWNLOAD_BASE}/download/RGEALTI/{archive}/{archive}.7z"
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            _resume_stream(session, url, part)
            part.replace(dest)
            return
        except requests.RequestException:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_RETRY_BASE_S * 2.0 ** attempt)


def _resume_stream(session: requests.Session, url: str, part: Path) -> None:
    """Stream the remainder of ``url`` onto ``part`` (Range resume)."""
    done = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={done}-"} if done else {}
    with session.get(url, headers=headers, stream=True,
                     timeout=_TIMEOUT_S) as resp:
        if done and resp.status_code == 416:      # already fully downloaded
            return
        resp.raise_for_status()
        # 206 continues the .part; anything else restarts it from byte 0.
        mode = "ab" if done and resp.status_code == 206 else "wb"
        with part.open(mode) as fh:
            for block in resp.iter_content(1024 * 1024):
                if block:
                    fh.write(block)


def _asc_to_tif(asc_path: Path, tif_path: Path) -> None:
    """Convert one ASC dalle to a tiled deflate GeoTIFF with CRS + nodata."""
    with rasterio.open(asc_path) as src:
        profile = src.profile
        data = src.read(1)
    profile.update(driver="GTiff", crs=CRS, nodata=NODATA,
                   compress="deflate", tiled=True,
                   blockxsize=256, blockysize=256)
    with rasterio.open(tif_path, "w", **profile) as dst:
        dst.write(data, 1)


def _extract_dalles(archive_path: Path, dep_dir: Path) -> None:
    """Extract every ASC dalle and convert it into ``dep_dir`` as GeoTIFF."""
    scratch = dep_dir / ".extract"
    shutil.rmtree(scratch, ignore_errors=True)
    with py7zr.SevenZipFile(archive_path) as archive:
        names = [n for n in archive.getnames() if n.lower().endswith(".asc")]
        if not names:
            raise RuntimeError(f"{archive_path.name} contains no ASC dalles")
        archive.extract(path=scratch, targets=names)
    for name in names:
        asc = scratch / name
        _asc_to_tif(asc, dep_dir / (Path(name).stem + ".tif"))
    shutil.rmtree(scratch, ignore_errors=True)


def _ensure_department(session: requests.Session, archive: str, zone: str,
                       cache_root: Path) -> Path:
    """Return the dalle directory for one department, downloading and
    converting its archive on first use. Safe across processes: the whole
    download + extract runs under an exclusive flock, and a marker file is
    written last so a killed extraction restarts cleanly."""
    dep_dir = cache_root / "rgealti_tiles" / zone
    marker = dep_dir / ".complete"
    if marker.exists():
        return dep_dir
    dep_dir.mkdir(parents=True, exist_ok=True)
    lock_path = dep_dir.with_suffix(".lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if marker.exists():
            return dep_dir
        archive_path = dep_dir / f"{archive}.7z"
        if not archive_path.exists():
            _download_archive(session, archive, archive_path)
        _extract_dalles(archive_path, dep_dir)
        archive_path.unlink()
        marker.touch()
    return dep_dir


def _dalle_bounds(path: Path) -> Bbox | None:
    """Dalle bounds from the round-kilometer NW corner its filename encodes."""
    match = _DALLE_RE.search(path.name)
    if match is None:
        return None
    west = float(match.group(1)) * 1000.0 - _HALF_CELL_M
    north = float(match.group(2)) * 1000.0 + _HALF_CELL_M
    return (west, north - TILE_M, west + TILE_M, north)


def _select_dalles(dep_dir: Path, bbox: Bbox) -> list[Path]:
    """Cached dalle GeoTIFFs in ``dep_dir`` intersecting ``bbox``."""
    minx, miny, maxx, maxy = bbox
    out: list[Path] = []
    for path in sorted(dep_dir.glob("*.tif")):
        bounds = _dalle_bounds(path)
        if bounds is None:
            continue
        if bounds[0] < maxx and bounds[2] > minx \
                and bounds[1] < maxy and bounds[3] > miny:
            out.append(path)
    return out
