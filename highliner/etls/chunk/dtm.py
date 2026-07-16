"""Fetch Digital Terrain Model elevation rasters.

ICGC serves the DTM through a WCS 1.0.0 endpoint as ESRI ArcGrid (ASCII):

    https://geoserveis.icgc.cat/icc_mdt/wcs/service
    COVERAGE=icc:met  (finest resolution available here is 5 m)

Each GetCoverage response is capped at ~140 KB (~35,800 pixels), so precompute
fetches each chunk as a grid of small tiles and merges them in memory.

IGN/IDEE serves the national MDT05 through OGC API Coverages. The code here
requests small COG subsets from the EPSG-specific 5 m collections.

Italy's HR-DTM-5m single-file source lives in ``dtm_hrdtm`` and is dispatched
from ``fetch_tiles`` like the sources above.
"""
import concurrent.futures
import fcntl
import functools
import hashlib
import json
import math
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.merge import merge
from shapely.geometry import box, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from highliner.etls.chunk import dtm_hrdtm, dtm_os

if TYPE_CHECKING:
    from highliner.models.raster import Raster

Bbox = tuple[float, float, float, float]

ICGC_WCS = "https://geoserveis.icgc.cat/icc_mdt/wcs/service"
COVERAGE_ID = "icc:met"
IDEE_COVERAGE_API = "https://api-coverages.idee.es/collections"
IDEE_COLLECTIONS = {
    "EPSG:25830": "EL.ElevationGridCoverage_25830_5_PB",
    "EPSG:4083": "EL.ElevationGridCoverage_4083_5_C",
}
CNIG_BASE = "https://centrodedescargas.cnig.es/CentroDescargas"
CNIG_HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}
NATIVE_RES = 5.0       # meters — finest DTM resolution on this WCS
MAX_TILE_PX = 175      # per side; 175*175 < 35,800 px request cap
TILE_WORKERS = 8       # concurrent tile downloads per fetch_tiles call
TILE_RETRY_ATTEMPTS = 4    # tries per tile before the transient failure is raised
TILE_RETRY_BASE_S = 2.0    # exponential backoff base; Retry-After wins if larger
NODATA = -9999.0
# ICGC encodes the sea surface with its own sentinel, distinct from the ArcGrid
# NODATA_VALUE (-9999) used for out-of-coverage. If left unmasked it reads as a
# real -8888 m elevation, so every coastal cell looks like an ~8888 m cliff and
# becomes a spurious anchor/zone. Treat it as nodata.
SEA_SENTINEL = -8888.0


def _retry_delay(attempt: int,
                 response: "requests.Response | None" = None) -> float:
    """Exponential backoff, bumped up to the server's Retry-After if larger."""
    retry_after = 0.0
    if response is not None:
        try:
            retry_after = float(response.headers.get("Retry-After", 0) or 0)
        except ValueError:                 # HTTP-date form; use the backoff
            retry_after = 0.0
    return max(retry_after, TILE_RETRY_BASE_S * 2.0 ** attempt)


def _download_with_retries(download: "Callable[[], Path]") -> Path:
    """Run ``download``, retrying transient HTTP failures (429/5xx/timeouts).
    Raises the last error once attempts are exhausted; RuntimeError (an
    out-of-coverage/bad-body response) is not retried."""
    for attempt in range(TILE_RETRY_ATTEMPTS):
        try:
            return download()
        except requests.RequestException as exc:
            if attempt == TILE_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_retry_delay(attempt, exc.response))
    raise RuntimeError("unreachable")


_CNIG_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


def _cnig_request(session: requests.Session, method: str, url: str,
                  **kwargs: Any) -> requests.Response:
    """Issue a CNIG request, retrying throttles/5xx/timeouts with backoff.
    Returns the final response; the caller still checks the status (e.g. via
    raise_for_status). A response that will be retried is closed first so a
    streamed body does not leak its connection."""
    for attempt in range(TILE_RETRY_ATTEMPTS):
        last = attempt == TILE_RETRY_ATTEMPTS - 1
        try:
            resp = session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            if last:
                raise
            time.sleep(_retry_delay(attempt, exc.response))
            continue
        if resp.status_code in _CNIG_RETRY_STATUS and not last:
            resp.close()
            time.sleep(_retry_delay(attempt, resp))
            continue
        return resp
    raise RuntimeError("unreachable")


def _download_tile(bbox: Bbox, width: int, height: int, dest: Path) -> Path:
    minx, miny, maxx, maxy = bbox
    params = {
        "SERVICE": "WCS",
        "REQUEST": "GetCoverage",
        "VERSION": "1.0.0",
        "CRS": "EPSG:25831",
        "COVERAGE": COVERAGE_ID,
        "FORMAT": "ArcGrid",
        "BBOX": f"{minx},{miny},{maxx},{maxy}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
    }
    r = requests.get(ICGC_WCS, params=params, timeout=120)
    r.raise_for_status()
    if not r.content.lstrip()[:5].upper().startswith(b"NCOLS"):
        raise RuntimeError(
            f"ICGC WCS did not return ArcGrid data: {r.content[:200]!r}")
    dest.write_bytes(r.content)
    return dest


def _epsg_code(crs: str) -> str:
    return crs.rsplit(":", 1)[-1]


def _download_idee_tile(bbox: Bbox, width: int, height: int, dest: Path,
                        crs: str) -> Path:
    collection = IDEE_COLLECTIONS.get(crs)
    if collection is None:
        raise RuntimeError(f"no IDEE MDT05 collection configured for {crs}")
    minx, miny, maxx, maxy = bbox
    params = {
        "f": "COG",
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "bbox-crs": f"http://www.opengis.net/def/crs/EPSG/0/{_epsg_code(crs)}",
    }
    url = f"{IDEE_COVERAGE_API}/{collection}/coverage"
    r = requests.get(url, params=params, timeout=180)
    r.raise_for_status()
    if not (r.content[:2] in (b"II", b"MM")
            or "tiff" in r.headers.get("content-type", "").lower()):
        raise RuntimeError(
            f"IDEE coverage did not return GeoTIFF data: {r.content[:200]!r}")
    dest.write_bytes(r.content)
    return dest


def _cnig_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(CNIG_HEADERS)
    return s


def _bbox_geom_lonlat(bbox: Bbox, crs: str) -> BaseGeometry:
    geom = box(*bbox)
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    return shapely_transform(transformer.transform, geom)


def _preferred_huso(crs: str) -> str | None:
    code = _epsg_code(crs)
    if code in {"25828", "4083"}:
        return "HU28"
    if code == "25829":
        return "HU29"
    if code == "25830":
        return "HU30"
    if code == "25831":
        return "HU31"
    return None


def _cnig_query_sheets(session: requests.Session, bbox: Bbox,
                       crs: str) -> list[tuple[str, str]]:
    geom = _bbox_geom_lonlat(bbox, crs)
    coords = json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": mapping(geom)}],
    })
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    page = 1
    while True:
        params = {
            "codAgr": "MOMDT",
            "codSerie": "MDT05",
            "numPagina": str(page),
            "codTipoArchivo": "",
            "codComAutonoma": "",
            "codProvincia": "",
            "codIne": "",
            "coordenadas": coords,
            "huso": "",
            "x": "",
            "y": "",
            "lon": "",
            "lat": "",
            "formato": "COG",
        }
        r = _cnig_request(session, "GET", f"{CNIG_BASE}/archivosSerie",
                          params=params, timeout=60)
        r.raise_for_status()
        secs = re.findall(r"detalleArchivo\?sec=(\d+)", r.text)
        names = re.findall(r"PNOA[-_]MDT05[^<\s]+", r.text)
        added = 0
        # Same caveat as the catalog scrape above: counts can drift.
        for sec, name in zip(secs, names, strict=False):
            if sec in seen:
                continue
            seen.add(sec)
            out.append((sec, name.replace("_", "-")))
            added += 1
        if added == 0:
            break
        page += 1

    huso = _preferred_huso(crs)
    if huso and any(huso in name for _sec, name in out):
        out = [(sec, name) for sec, name in out if huso in name]
    return out


def _cached_query_sheets(session: requests.Session, bbox: Bbox, crs: str,
                         cache_dir: Path) -> list[tuple[str, str]]:
    """Resolve intersecting MDT05 sheets for ``(bbox, crs)``, caching the CNIG
    catalog query to disk. The chunk grid is deterministic, so re-runs and
    adjacent chunks reuse the cached resolution instead of re-querying CNIG.
    Safe across processes: one file per key, written atomically (tmp keyed by
    pid + replace); the sole caller runs one chunk per process, so same-key
    threads never race on the tmp file."""
    key = hashlib.sha1(json.dumps([crs, list(bbox)]).encode()).hexdigest()
    path = cache_dir / f"{key}.json"
    if path.exists():
        return [tuple(row) for row in json.loads(path.read_text())]
    # Empty results are cached too, so sea/no-coverage chunks stop re-querying.
    # This assumes an empty resolution is genuine: _cnig_query_sheets only
    # returns [] after real 200 pages (429/5xx are retried in _cnig_request),
    # so a throttle can't be mistaken for "no sheets" and cached permanently.
    sheets = _cnig_query_sheets(session, bbox, crs)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(sheets))
    tmp.replace(path)
    return sheets


def _download_cnig_sheet(session: requests.Session, sec: str, filename: str,
                         dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    lock_path = dest.with_suffix(dest.suffix + ".lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        _cnig_request(session, "GET", f"{CNIG_BASE}/detalleArchivo",
                      params={"sec": sec}, timeout=60)
        r = _cnig_request(session, "GET", f"{CNIG_BASE}/initDescargaDir",
                          params={"secuencial": sec}, timeout=60)
        r.raise_for_status()
        sec_download = str(r.json()["secuencialDescDir"])
        data = {
            "secuencial": sec,
            "secDescDirLA": sec_download,
            "codSerie": "MDT05",
            "urlCart": "",
            "id_productor": "",
            "codNumMD": "",
            "avisoLimiteFiles": "",
        }
        tmp = dest.with_suffix(dest.suffix + f".{os.getpid()}.part")
        resp = _cnig_request(session, "POST", f"{CNIG_BASE}/descargaDir",
                             data=data, stream=True, timeout=300)
        with resp:
            resp.raise_for_status()
            if "tiff" not in resp.headers.get("content-type", "").lower():
                head = resp.raw.read(200, decode_content=True)
                raise RuntimeError(f"CNIG did not return GeoTIFF data: {head!r}")
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(1024 * 1024):
                    if chunk:
                        fh.write(chunk)
        tmp.replace(dest)
    return dest


def _fetch_cnig_tiles(bbox: Bbox, cache_root: Path, crs: str) -> list[Path]:
    """Fetch CNIG MDT05 sheets into the persistent ``cache_root``.

    National sheets and the sheet-index resolution are reused across regions
    and re-runs, so they live in a country-scoped cache outside the per-region
    data tree and can be wiped without touching precomputed output."""
    cache_root = Path(cache_root)
    session = _cnig_session()
    out: list[Path] = []
    cache_dir = cache_root / "mdt05_tiles"
    index_dir = cache_root / "mdt05_sheet_index"
    for sec, filename in _cached_query_sheets(session, bbox, crs, index_dir):
        dest = cache_dir / filename
        # Retry the whole sheet download: the response body is streamed
        # (stream=True), so a mid-transfer connection drop (IncompleteRead ->
        # ChunkedEncodingError) surfaces here, outside _cnig_request's
        # request-phase retry. Without this a single broken stream aborts the
        # entire precompute run. _download_cnig_sheet writes to a .part file and
        # skips a completed dest, so re-running it is safe.
        out.append(_download_with_retries(
            functools.partial(_download_cnig_sheet, session, sec, filename, dest)))
    return out


def _snap(bbox: Bbox, res: float) -> Bbox:
    minx, miny, maxx, maxy = (float(v) for v in bbox)
    return (math.floor(minx / res) * res, math.floor(miny / res) * res,
            math.ceil(maxx / res) * res, math.ceil(maxy / res) * res)


def tile_specs(bbox: Bbox, res: float = NATIVE_RES, tile_px: int = MAX_TILE_PX
               ) -> list[tuple[Bbox, int, int]]:
    """Tile (bbox, width, height) specs tiling ``bbox`` snapped to the res grid."""
    minx, miny, maxx, maxy = _snap(bbox, res)
    step = tile_px * res
    out: list[tuple[Bbox, int, int]] = []
    y = miny
    while y < maxy:
        ty2 = min(y + step, maxy)
        x = minx
        while x < maxx:
            tx2 = min(x + step, maxx)
            w = int(round((tx2 - x) / res))
            h = int(round((ty2 - y) / res))
            if w > 0 and h > 0:
                out.append(((x, y, tx2, ty2), w, h))
            x = tx2
        y = ty2
    return out


def _fetch_from_cache(source: str, bbox: Bbox, crs: str,
                      cache_dir: Path | None) -> list[Path]:
    """Dispatch the sources whose downloads persist in the country cache."""
    if cache_dir is None:
        raise ValueError(f"{source} source requires cache_dir")
    if source == "cnig":
        return _fetch_cnig_tiles(bbox, cache_dir, crs)
    if source == "hrdtm":
        return dtm_hrdtm.fetch_hrdtm(cache_dir)
    if source == "os_terrain_50":
        return dtm_os.fetch_os_terrain_50(bbox, cache_dir)
    return dtm_os.fetch_osni_dtm_10m(bbox, cache_dir)


def fetch_tiles(bbox: Bbox, tiles_dir: Path, res: float = NATIVE_RES,  # noqa: PLR0913
                tile_px: int = MAX_TILE_PX, source: str = "icgc",
                crs: str = "EPSG:25831",
                cache_dir: Path | None = None) -> list[Path]:
    """Download tiles covering ``bbox`` into ``tiles_dir``; reuse cached tiles;
    skip tiles whose response body is not raster data (out of coverage).
    Transient HTTP failures (rate limits, 5xx, timeouts) are retried with
    backoff and raised once ``TILE_RETRY_ATTEMPTS`` is exhausted, so a
    throttled run fails loudly instead of writing holes into the terrain.
    Returns the paths that exist on disk. The ``cnig`` and ``hrdtm`` sources
    ignore ``tiles_dir`` (their sheets persist in ``cache_dir``, required for
    them)."""
    tiles_dir = Path(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)
    if source in ("cnig", "hrdtm", "os_terrain_50", "osni_dtm_10m"):
        return _fetch_from_cache(source, bbox, crs, cache_dir)
    if source not in ("icgc", "idee"):
        raise RuntimeError(f"unknown DTM source '{source}'")

    def fetch_one(spec: tuple[Bbox, int, int]) -> Path | None:
        tb, w, h = spec
        ext = "tif" if source == "idee" else "asc"
        dest = tiles_dir / f"t_{int(tb[0])}_{int(tb[1])}.{ext}"
        if not dest.exists():
            try:
                if source == "icgc":
                    _download_with_retries(lambda: _download_tile(tb, w, h, dest))
                else:
                    _download_with_retries(
                        lambda: _download_idee_tile(tb, w, h, dest, crs))
            except RuntimeError:
                return None       # out of coverage / non-raster body: expected
        return dest

    specs = tile_specs(bbox, res, tile_px)
    if not specs:
        return []
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(TILE_WORKERS, len(specs))) as pool:
        results = list(pool.map(fetch_one, specs))   # map preserves spec order
    return [p for p in results if p is not None]


def raster_from_tiles(paths: list[Path], res: float = NATIVE_RES,
                      bbox: Bbox | None = None) -> "Raster | None":
    """Merge tile rasters into one in-memory ``Raster`` (NaN nodata), or None."""
    from highliner.models.raster import Raster
    if not paths:
        return None
    srcs = [rasterio.open(p) for p in paths]
    try:
        arr, transform = merge(srcs, nodata=NODATA, bounds=bbox)
    finally:
        for s in srcs:
            s.close()
    data = arr[0].astype("float32")
    data[(data == NODATA) | (data == SEA_SENTINEL)] = np.nan
    return Raster(data=data, transform=transform, res=abs(transform.a))
