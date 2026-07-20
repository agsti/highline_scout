"""CNIG and IGN/IDEE clients for Spain's national MDT05.

CNIG serves 1:25,000 sheets through a download portal; IDEE serves the same
model as COG subsets through OGC API Coverages. Sheets persist in the country
cache rather than the per-chunk tiles directory.
"""
import fcntl
import functools
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from shapely.geometry import mapping

from highliner.etls.chunk.dtm_core import (
    TILE_RETRY_ATTEMPTS,
    Bbox,
    _bbox_geom_lonlat,
    _download_with_retries,
    _epsg_code,
    _retry_delay,
    fetch_tile_grid,
)

IDEE_COVERAGE_API = "https://api-coverages.idee.es/collections"
IDEE_COLLECTIONS = {
    "EPSG:25830": "EL.ElevationGridCoverage_25830_5_PB",
    "EPSG:4083": "EL.ElevationGridCoverage_4083_5_C",
}
CNIG_BASE = "https://centrodedescargas.cnig.es/CentroDescargas"
CNIG_HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}

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


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="cnig"``.

    CNIG is a bulk-sheet source: downloads persist in the country cache, so
    ``tiles_dir`` is ignored.
    """
    if cache_dir is None:
        raise ValueError("cnig source requires cache_dir")
    return _fetch_cnig_tiles(bbox, cache_dir, crs)


def fetch_idee(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
               crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="idee"``.

    IDEE is a coverage API rather than a bulk product, so the bbox is tiled and
    each tile requested in the region's CRS. Ignores ``cache_dir``.
    """
    def download(tile_bbox: Bbox, width: int, height: int,
                 dest: Path) -> Path:
        return _download_idee_tile(tile_bbox, width, height, dest, crs)

    return fetch_tile_grid(bbox, tiles_dir, download, ext="tif")
