"""Fetch INEGI's public 5 m bare-earth terrain sheets for Mexico.

INEGI's MDE catalogue distinguishes ``Terreno`` from its surface product; this
client requests only the 5 m ``Terreno`` sheets, caches their ASCII archives,
and reprojects selected sheets into the region CRS for the chunk pipeline.

The ASCII product is not uniform. Over a 60-sheet sample of the catalogue,
archives came in three layouts (``conjunto_de_datos``/``metadatos`` with either
separator, and ``MT_XYZ``/``MT_Auxiliares``/``MT_Metadatos``) and the UTM zone —
which picks the sheet's native CRS — was declared three different ways, or not
at all. So the zone is read from whichever dialect the sheet uses and falls back
to the sheet key, whose ``<letter><zone>`` prefix names the 1:1,000,000 chart
the sheet subdivides. That fallback is the reliable one: where a sheet declares
both a zone and a central meridian, the two can disagree (``D15B53A3`` says
zone 15 with ``<longcm>-099``, a zone-14 meridian) and it is the zone, matching
the key, that agrees with the sheet's own longitude bounds.
"""
import fcntl
import re
import zipfile
from pathlib import Path
from typing import Any, cast

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject

from highliner.etls.chunk.dtm_core import NODATA, _download_with_retries

Bbox = tuple[float, float, float, float]
CATALOGUE_URL = "https://www.inegi.org.mx/app/geo2/elevacionesmex/getFormato10k.do"
DETAIL_URL = "https://www.inegi.org.mx/app/geo2/elevacionesmex/getF10KDescarga.do"
_SHEET_MARGIN_M = 6_000
_XYZ_MEMBER = re.compile(r"\.xyz$")
# "<sheet>_mt.txt" in the common layout, "<sheet>_mt_ntm.txt" (or "_ntm_a") in
# the variant one; the archive-wide "metadato_mdt.txt" must not match.
_METADATA_MEMBER = re.compile(r"_mt(_ntm[a-z_]*)?\.txt$")
# Plain-text sheets state the zone in prose; the two XML dialects tag it as
# <utm_zone> or <utmzone>. The MT_Auxiliares layout states no zone at all.
_UTM_ZONE_PATTERNS = (r"N.mero de zona UTM:\s*(\d+)", r"<utm_?zone>\s*(\d+)")
_KEY_ZONE = re.compile(r"^[a-z](\d{2})", re.IGNORECASE)


class SheetUnavailable(RuntimeError):
    """A catalogued sheet INEGI publishes no ASCII terrain archive for."""


def _catalogue() -> list[dict[str, Any]]:
    response = requests.post(CATALOGUE_URL, data={"res": "5", "mod": "T"}, timeout=300)
    response.raise_for_status()
    return cast(list[dict[str, Any]], response.json())


def _sheet_keys_for_bbox(catalogue: list[dict[str, Any]], bbox: Bbox,
                         crs: str) -> list[str]:
    """Return 5 m sheet keys whose catalogue centres meet the chunk halo."""
    transformer = Transformer.from_crs(crs, "EPSG:3857", always_xy=True)
    minx, miny = transformer.transform(bbox[0], bbox[1])
    maxx, maxy = transformer.transform(bbox[2], bbox[3])
    west, east = sorted((minx, maxx))
    south, north = sorted((miny, maxy))
    return [str(item["cve"]) for item in catalogue
            if west - _SHEET_MARGIN_M <= float(item["x"]) <= east + _SHEET_MARGIN_M
            and south - _SHEET_MARGIN_M <= float(item["y"]) <= north + _SHEET_MARGIN_M]


def _archive_url(records: list[dict[str, Any]]) -> str:
    """Return the first (latest) ASCII archive URL offered for a sheet."""
    for record in records:
        archive = str(record.get("archivo", ""))
        if "_as.zip" in archive:
            return f"{record['url_descarga']}_as.zip"
    raise SheetUnavailable("INEGI catalogue has no ASCII terrain archive")


def _member(names: list[str], pattern: re.Pattern[str]) -> str | None:
    """Match ``pattern`` against each member's basename, either separator."""
    for name in names:
        if pattern.search(name.replace("\\", "/").rsplit("/", 1)[-1].lower()):
            return name
    return None


def _utm_zone(key: str, metadata: bytes | None) -> int:
    """The sheet's UTM zone: whichever dialect its metadata declares, else the
    zone of the 1:1,000,000 chart its key subdivides."""
    text = "" if metadata is None else metadata.decode("latin-1", errors="replace")
    for pattern in _UTM_ZONE_PATTERNS:
        match = re.search(pattern, text)
        if match is not None:
            return int(match[1])
    from_key = _KEY_ZONE.match(key)
    if from_key is None:
        raise RuntimeError(f"INEGI sheet {key} declares no UTM zone")
    return int(from_key[1])


def _write_xyz_grid(xyz: bytes, zone: int, dest: Path) -> None:
    """Convert INEGI's regular XYZ export into a GeoTIFF in UTM ``zone``."""
    points = np.loadtxt(xyz.splitlines(), dtype="float32")
    xs = np.unique(points[:, 0])
    ys = np.unique(points[:, 1])
    data = np.full((len(ys), len(xs)), NODATA, dtype="float32")
    columns = np.searchsorted(xs, points[:, 0])
    rows = len(ys) - 1 - np.searchsorted(ys, points[:, 1])
    data[rows, columns] = points[:, 2]
    transform = from_origin(float(xs.min()) - 2.5, float(ys.max()) + 2.5, 5, 5)
    with rasterio.open(dest, "w", driver="GTiff", width=len(xs), height=len(ys),
                       count=1, dtype="float32", crs=f"EPSG:{6355 + zone}",
                       transform=transform, nodata=NODATA) as out:
        out.write(data, 1)


def _download_sheet(key: str, dest: Path) -> None:
    response = requests.post(DETAIL_URL, data={"res": "5", "mod": "T", "cve": key},
                             timeout=300)
    response.raise_for_status()
    records = response.json()
    if not records:
        raise SheetUnavailable(f"INEGI has no 5 m terrain sheet for {key}")
    with requests.get(_archive_url(records), stream=True, timeout=300) as archive:
        archive.raise_for_status()
        zip_path = dest.with_suffix(".zip")
        with zip_path.open("wb") as fh:
            for block in archive.iter_content(1024 * 1024):
                if block:
                    fh.write(block)
    try:
        with zipfile.ZipFile(zip_path) as zipped:
            names = zipped.namelist()
            xyz = _member(names, _XYZ_MEMBER)
            metadata = _member(names, _METADATA_MEMBER)
            if xyz is None:
                raise RuntimeError(f"INEGI terrain archive for {key} lacks XYZ")
            zone = _utm_zone(key, None if metadata is None else zipped.read(metadata))
            _write_xyz_grid(zipped.read(xyz), zone, dest)
    finally:
        # Never leave the multi-MB download in the persistent cache: only the
        # .tif is looked up on the next run, so a stale .zip is pure leak.
        zip_path.unlink(missing_ok=True)


def _cached_sheet(key: str, cache_dir: Path) -> Path:
    dest = cache_dir / "inegi_mdt5" / f"{key}.tif"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not dest.exists():
            _download_with_retries(lambda: _download_sheet(key, dest))
    return dest


def _reproject(source: Path, dest: Path, crs: str) -> Path:
    with rasterio.open(source) as src:
        transform, width, height = calculate_default_transform(
            src.crs, crs, src.width, src.height, *src.bounds, resolution=5)
        profile = src.profile.copy()
        profile.update(driver="GTiff", crs=crs, transform=transform, width=width,
                       height=height, nodata=NODATA, dtype="float32")
        with rasterio.open(dest, "w", **profile) as out:
            reproject(rasterio.band(src, 1), rasterio.band(out, 1),
                      src_transform=src.transform, src_crs=src.crs,
                      src_nodata=src.nodata, dst_transform=transform, dst_crs=crs,
                      dst_nodata=NODATA, resampling=rasterio.enums.Resampling.bilinear)
    return dest


def _sheet_tile(key: str, tiles_dir: Path, cache_dir: Path, crs: str) -> Path | None:
    """Reproject one sheet, or None where the source publishes no archive."""
    try:
        source = _cached_sheet(key, cache_dir)
    except SheetUnavailable:
        return None
    return _reproject(source, tiles_dir / f"{key}.tif", crs)


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetch, cache, and reproject INEGI 5 m terrain sheets for one chunk."""
    if cache_dir is None:
        raise ValueError("INEGI terrain source requires cache_dir")
    tiles_dir = Path(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)
    keys = _sheet_keys_for_bbox(_catalogue(), bbox, crs)
    tiles = [_sheet_tile(key, tiles_dir, Path(cache_dir), crs) for key in keys]
    return [tile for tile in tiles if tile is not None]
