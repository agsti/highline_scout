"""Fetch CIREN's ALOS PALSAR 12.5 m DEM mosaics covering Chile.

CIREN (Centro de Información de Recursos Naturales, published via the
national geoportal.cl catalog) distributes one RAR archive per administrative
region, each a JPEG2000 raster in UTM (zone 18S or 19S depending on the
region's longitude) built from JAXA's ALOS PALSAR radar mission and adjusted
to orthometric heights via EGM2008. 12.5 m is coarser than this pipeline's
usual 5 m target (and the skill's 10 m floor) — it is the finest bare-earth
national elevation product publicly available for Chile; cliff faces below
~12.5 m will not be resolved. Out-of-coverage/void cells are plain integer 0
in the source; there is no separate sea sentinel.

Archives carry inconsistent embedded georeferencing (some rasters have a
GeoJP2 box, some don't), so this fetcher prefers deriving CRS + transform
from an archive's ``.j2w``/``.prj`` sidecars over trusting the JP2 itself
whenever that pair ships alongside it. At least one region (biobio) ships no
sidecars at all, relying entirely on a correct embedded GMLJP2 box - so a
missing sidecar pair falls back to the JP2's own CRS/transform rather than
being treated as a broken archive. Extraction needs the `unar` CLI (The
Unarchiver): some sidecar files use a RAR compression method `py7zr`/`7z`
don't implement, while `unar` extracts every member cleanly. Install it
system-wide (``apt-get install unar`` / ``brew install unar``) before running
this ETL.

Bulk-archive pattern like Italy's HR-DTM: each region's archive is downloaded
once into the persistent country cache, converted to a nodata-tagged deflate
GeoTIFF, and every chunk afterwards is a local windowed read (via
``raster_from_tiles``'s ``bounds=`` merge), with no per-chunk network traffic.
"""
from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
import requests
from affine import Affine
from pyproj import CRS
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject
from rasterio.windows import Window
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

Bbox = tuple[float, float, float, float]
NODATA = -9999.0
_TIMEOUT_S = 300
_RETRY_ATTEMPTS = 6
_RETRY_BASE_S = 3.0
_HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}


@dataclass(frozen=True)
class RegionArchive:
    """One CIREN ALOS PALSAR regional mosaic and its coverage."""

    name: str
    url: str
    lonlat_bbox: Bbox      # (west, south, east, north)
    epsg: int              # expected UTM zone the archive is published in
    member: str | None = None   # nested sub-archive name fragment, if any
    download_key: str | None = None   # shared cache key when member is set


# Coverage bboxes and download links resolved from each region's ISO 19139
# metadata record on geoportal.cl (catalog ids 35424-35439); EPSG is the
# standard UTM-zone-from-longitude formula, confirmed against the actual
# embedded/sidecar CRS for los_rios (18S) and arica_y_parinacota (19S).
# Magallanes' bbox spans multiple UTM zones and its archive turns out to be
# a container of two nested per-zone sub-archives (norte 18S / sur 19S);
# both share one download but produce two regions, so they carry an
# explicit `member` + shared `download_key` (bbox/epsg measured from each
# nested raster's own world file + shape, not the combined-region metadata).
CATALOG: tuple[RegionArchive, ...] = (
    RegionArchive("arica_y_parinacota",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "2299324e-1202-3274-9fad-1df1a4ccd092",
                 (-70.793, -19.233, -68.448, -17.541), 32719),
    RegionArchive("tarapaca",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "3d26f8eb-4795-3a8d-be9d-d632809958d0",
                 (-70.989, -21.939, -67.573, -18.703), 32719),
    RegionArchive("antofagasta",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "f77f1be6-3dfc-37ce-a689-3f72022d301f",
                 (-71.136, -26.230, -66.797, -20.641), 32719),
    RegionArchive("atacama",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "f5bd4746-86c8-3471-83a6-7b269cde61df",
                 (-71.519, -29.319, -68.105, -24.985), 32719),
    RegionArchive("coquimbo",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "8de93ad0-9518-303d-8530-ef08ce32420f",
                 (-72.515, -32.568, -69.555, -28.736), 32719),
    RegionArchive("valparaiso",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "b538717f-cc50-3c8e-bd28-2aff59d4f4e5",
                 (-71.980, -33.729, -69.630, -31.861), 32719),
    RegionArchive("metropolitana",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "50d4c190-6c3a-3b09-be2f-3d571960fea0",
                 (-71.931, -34.369, -69.389, -32.564), 32719),
    RegionArchive("ohiggins",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "b18a60c9-1f2f-3c99-979e-c788330cda91",
                 (-72.213, -35.142, -69.700, -33.660), 32719),
    RegionArchive("maule",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "9402ade6-0586-3f38-b16e-d5b1853e2d80",
                 (-72.950, -36.596, -70.098, -34.521), 32719),
    RegionArchive("nuble",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "aff5914a-6d62-30a6-861c-c1e6877f946d",
                 (-74.134, -37.274, -70.465, -35.866), 32718),
    RegionArchive("biobio",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "d244d77d-b707-35f2-bfe4-a39e80931d0a",
                 (-74.122, -38.483, -70.774, -35.613), 32718),
    RegionArchive("araucania",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "5298540a-7e41-39e4-aac1-939cdab44460",
                 (-74.115, -39.758, -70.422, -37.505), 32718),
    RegionArchive("los_rios",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "69bf2b66-4f52-3947-af25-314e7529872a",
                 (-73.838, -40.645, -71.425, -39.166), 32718),
    RegionArchive("los_lagos",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "bf3fb01f-3e1f-39c6-8fb4-98d31ccc6262",
                 (-75.245, -44.084, -71.286, -39.973), 32718),
    RegionArchive("aysen",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "80827597-7484-333a-adc6-3f84714bf28d",
                 (-75.699, -49.539, -70.970, -43.322), 32718),
    RegionArchive("magallanes_norte",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "dd64b5cd-078f-3442-b599-83251a48311b",
                 (-76.062, -51.864, -71.502, -48.530), 32718,
                 member="norte", download_key="magallanes"),
    RegionArchive("magallanes_sur",
                 "https://geoportal.cl/geoportal/catalog/download/"
                 "dd64b5cd-078f-3442-b599-83251a48311b",
                 (-76.412, -56.004, -66.163, -51.381), 32719,
                 member="sur", download_key="magallanes"),
)



# A chunk's requested bbox is its core plus config.CHUNK_HALO_M (1050 m); at
# the outermost chunk of a region that halo pokes past the region's own
# lonlat_bbox (the same rectangle the chunk grid was built from - see
# chile/main.py's _region_bbox), and every region's lonlat_bbox is itself a
# rounded rectangle read off ISO 19139 metadata, not the archive's true
# extent. Both effects can leave a sliver of the halo outside every declared
# rectangle even though it's still core-adjacent, real coverage. 0.05 deg is
# generous versus the halo's worst-case reach (~0.017 deg at Chile's
# southernmost latitudes) while staying far short of the gap between
# genuinely non-adjacent archives, so a bbox still unmatched after this
# retry is a real coverage gap, not edge rounding.
_EDGE_TOLERANCE_DEG = 0.05


def _match_archive(bbox: Bbox, crs: str) -> RegionArchive | None:
    """Find the archive covering ``bbox``, preferring the nearest region
    center among same-zone candidates. Adjacent regions' rectangular
    coverage commonly overlaps at the (irregular) real border, so a chunk's
    halo can poke into a neighbor's declared extent - picking by nearest
    center keeps that a stable, home-region choice rather than whichever
    entry happens to come first in ``CATALOG``.

    Returns None when no archive covers ``bbox`` even with the edge
    tolerance applied. A region's UTM grid is built from a bounding box of
    its lonlat rectangle's corners (see chile/main.py's ``_region_bbox``),
    which - because UTM meridian convergence skews a lonlat rectangle into a
    quadrilateral - can overestimate true coverage by much more than
    ``_EDGE_TOLERANCE_DEG`` for regions spanning a wide latitude range (e.g.
    antofagasta). The outermost chunks of such a region's grid can then fall
    genuinely outside Chile (typically over the Andes into Argentina), where
    no archive - rightly - exists; that's a real absence of data, not a bug,
    so it's handled like any other no-coverage chunk (empty tile list)."""
    epsg = int(crs.rsplit(":", 1)[-1])
    lonlat = _to_lonlat(bbox, crs)
    query = box(*lonlat)
    qx, qy = query.centroid.x, query.centroid.y

    def matches(geom: BaseGeometry) -> list[RegionArchive]:
        return [entry for entry in CATALOG if entry.epsg == epsg
               and box(*entry.lonlat_bbox).intersects(geom)]

    candidates = matches(query) or matches(query.buffer(_EDGE_TOLERANCE_DEG))
    if not candidates:
        return None

    def dist(entry: RegionArchive) -> float:
        center = box(*entry.lonlat_bbox).centroid
        return float((center.x - qx) ** 2 + (center.y - qy) ** 2)

    return min(candidates, key=dist)


def _to_lonlat(bbox: Bbox, crs: str) -> Bbox:
    from pyproj import Transformer
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    minx, miny, maxx, maxy = bbox
    xs, ys = [], []
    for x, y in ((minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)):
        lon, lat = transformer.transform(x, y)
        xs.append(lon)
        ys.append(lat)
    return (min(xs), min(ys), max(xs), max(ys))


def _download(url: str, dest: Path) -> None:
    """Stream one region archive to ``dest``, resuming dropped connections
    and verifying the final size against the server's declared total (a
    connection can end early without `requests` ever raising)."""
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            total = _resume_stream(url, part)
            if total is not None and part.stat().st_size != total:
                raise requests.exceptions.ChunkedEncodingError(
                    f"{url}: got {part.stat().st_size} bytes, expected {total}")
            part.replace(dest)
            return
        except requests.RequestException:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_RETRY_BASE_S * 2.0 ** attempt)


def _resume_stream(url: str, part: Path) -> int | None:
    """Stream the remainder of ``url`` onto ``part``; returns the total
    expected size if the server reports one, else None."""
    done = part.stat().st_size if part.exists() else 0
    headers = {**_HEADERS, "Range": f"bytes={done}-"} if done else dict(_HEADERS)
    with requests.get(url, headers=headers, stream=True,
                     timeout=_TIMEOUT_S) as resp:
        if done and resp.status_code == 416:
            return done
        resp.raise_for_status()
        mode = "ab" if done and resp.status_code == 206 else "wb"
        with part.open(mode) as fh:
            for block in resp.iter_content(1024 * 1024):
                if block:
                    fh.write(block)
        content_range = resp.headers.get("Content-Range")
        if content_range and "/" in content_range:
            total_str = content_range.rsplit("/", 1)[-1]
            return int(total_str) if total_str != "*" else None
        content_length = resp.headers.get("Content-Length")
        if content_length is None:
            return None
        return (done if mode == "ab" else 0) + int(content_length)


def _run_unar(archive_path: Path, dest_dir: Path) -> None:
    if shutil.which("unar") is None:
        raise RuntimeError(
            "the `unar` CLI is required to extract ALOS PALSAR archives "
            "(some sidecar files use a RAR compression method 7z/py7zr "
            "cannot read) - install it with `apt-get install unar` or "
            "`brew install unar`")
    subprocess.run(["unar", "-f", "-q", "-o", str(dest_dir), str(archive_path)],
                   check=True, capture_output=True)


def _parse_world_file(path: Path) -> Affine:
    values = [float(line.strip()) for line in path.read_text().splitlines()
              if line.strip()]
    pixel_w, row_rot, col_rot, pixel_h, center_x, center_y = values
    if row_rot != 0.0 or col_rot != 0.0:
        raise RuntimeError(f"{path}: rotated world file not supported")
    corner_x = center_x - abs(pixel_w) / 2.0
    corner_y = center_y - pixel_h / 2.0
    return Affine(pixel_w, 0.0, corner_x, 0.0, pixel_h, corner_y)


def _parse_prj_epsg(path: Path) -> int:
    epsg = CRS.from_wkt(path.read_text()).to_epsg()
    if epsg is None:
        raise RuntimeError(f"{path}: could not resolve an EPSG code")
    return epsg


def _extract_member(extract_dir: Path, member: str) -> Path:
    """Some huge regions (Magallanes) ship as a container of nested per-zone
    sub-archives rather than a single raster; unpack the one matching
    ``member`` (e.g. "norte"/"sur") into its own subfolder."""
    nested = [p for p in extract_dir.rglob("*.rar") if member.lower() in p.name.lower()]
    if len(nested) != 1:
        raise RuntimeError(
            f"{extract_dir}: expected exactly one nested archive matching "
            f"'{member}', found {len(nested)}")
    member_dir = extract_dir / f"_member_{member}"
    _run_unar(nested[0], member_dir)
    return member_dir


_NATIVE_RES_M = 12.5  # ALOS PALSAR's native ground resolution


def _reproject_to_epsg(src: rasterio.DatasetReader, dst_epsg: int,
                       res: float = _NATIVE_RES_M) -> tuple[np.ndarray, Affine]:
    """Resample ``src``'s band 1 into ``dst_epsg`` at ``res`` meters/pixel."""
    dst_crs = f"EPSG:{dst_epsg}"
    transform, width, height = calculate_default_transform(
        src.crs, dst_crs, src.width, src.height, *src.bounds, resolution=res)
    dst = np.zeros((height, width), dtype="float32")
    reproject(source=rasterio.band(src, 1), destination=dst,
             src_transform=src.transform, src_crs=src.crs, src_nodata=0.0,
             dst_transform=transform, dst_crs=dst_crs, dst_nodata=0.0,
             resampling=Resampling.bilinear)
    return dst, transform


_STREAM_ROWS = 4096  # row-strip height for windowed conversion; bounds peak
                     # memory regardless of full raster size (magallanes_sur
                     # alone is ~2 billion pixels - a single float32 read of
                     # the whole band plus its uint16 source briefly needs
                     # >12 GB and OOM-killed a production worker)


def _geotiff_profile(width: int, height: int, epsg: int,
                     transform: Affine) -> dict[str, object]:
    return {
        "driver": "GTiff", "dtype": "float32", "count": 1,
        "width": width, "height": height,
        "crs": f"EPSG:{epsg}", "transform": transform, "nodata": NODATA,
        "compress": "deflate", "tiled": True,
        "blockxsize": 256, "blockysize": 256,
    }


def _write_streamed(src: rasterio.DatasetReader, dest: Path, epsg: int,
                    transform: Affine) -> None:
    """Copy ``src``'s band 1 into a nodata-tagged GeoTIFF in row strips, so
    peak memory stays bounded even for a multi-billion-pixel source (unlike
    reading the whole band into one array)."""
    tmp = dest.with_suffix(f".tif.{os.getpid()}.tmp")
    profile = _geotiff_profile(src.width, src.height, epsg, transform)
    with rasterio.open(tmp, "w", **profile) as dst:
        for row in range(0, src.height, _STREAM_ROWS):
            window = Window(0, row, src.width, min(_STREAM_ROWS, src.height - row))
            block = src.read(1, window=window).astype("float32")
            block[block == 0.0] = NODATA
            dst.write(block, 1, window=window)
    tmp.replace(dest)


def _convert_to_geotiff(extract_dir: Path, dest: Path, expected_epsg: int,
                        member: str | None = None) -> None:
    """Convert the extracted JP2 into a nodata-tagged GeoTIFF.

    Most archives ship matching ``.j2w``/``.prj`` sidecars, and those are
    preferred over the JP2's own georeferencing when present (the module
    docstring's "some rasters have a GeoJP2 box, some don't" - sidecars are
    the more uniform source). At least two archives ship no sidecars at all
    and rely entirely on an embedded GMLJP2 box, but that box is itself
    inconsistent between them: biobio's is a correct projected UTM CRS
    matching its declared region outright, while nuble's is - despite
    otherwise-correct extent/origin - a geographic (lon/lat degrees) CRS
    that was never the expected projected one. Rather than special-case
    known-good archives, any sidecar-less JP2 whose own CRS doesn't already
    match ``expected_epsg`` is resampled into it (native ALOS PALSAR
    resolution, bilinear - elevation is continuous), so this keeps working
    for both today's cases and future ones without a name-matched hack.

    The no-reprojection paths (sidecars, or an already-matching embedded
    CRS) stream the conversion in row strips rather than materializing the
    whole band - some archives (Magallanes) are large enough that a single
    dense float32 copy of the band would exhaust memory on its own."""
    search_dir = _extract_member(extract_dir, member) if member else extract_dir
    jp2_paths = list(search_dir.rglob("*.jp2"))
    j2w_paths = list(search_dir.rglob("*.j2w"))
    prj_paths = list(search_dir.rglob("*.prj"))
    if len(jp2_paths) != 1 or len(j2w_paths) != len(prj_paths) or len(j2w_paths) > 1:
        raise RuntimeError(
            f"{search_dir}: expected exactly one .jp2 and a matched .j2w/"
            f".prj pair (or neither), found "
            f"{len(jp2_paths)}/{len(j2w_paths)}/{len(prj_paths)}")
    with rasterio.open(jp2_paths[0]) as src:
        if j2w_paths:
            transform = _parse_world_file(j2w_paths[0])
            epsg = _parse_prj_epsg(prj_paths[0])
            if epsg != expected_epsg:
                raise RuntimeError(
                    f"{extract_dir}: archive is EPSG:{epsg}, region "
                    f"declared EPSG:{expected_epsg}")
            _write_streamed(src, dest, epsg, transform)
            return
        if src.crs is not None and src.crs.to_epsg() == expected_epsg:
            _write_streamed(src, dest, expected_epsg, src.transform)
            return
        if src.crs is None:
            raise RuntimeError(
                f"{search_dir}: no sidecars and the JP2 carries no "
                f"embedded CRS either")
        data, transform = _reproject_to_epsg(src, expected_epsg)
    data[data == 0.0] = NODATA
    tmp = dest.with_suffix(f".tif.{os.getpid()}.tmp")
    profile = _geotiff_profile(data.shape[1], data.shape[0], expected_epsg, transform)
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(data, 1)
    tmp.replace(dest)


def _ensure_region_geotiff(entry: RegionArchive, cache_root: Path) -> Path:
    """Return the cached, converted GeoTIFF for one region, building it once.

    Safe across processes: the whole download + extract + convert runs under
    an exclusive flock, and the GeoTIFF is written to a temp path and
    `.replace()`d onto the final name only once complete."""
    root = Path(cache_root) / "alos_palsar"
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{entry.name}.tif"
    if dest.exists():
        return dest
    # Split-archive siblings (magallanes_norte/_sur) share one download and
    # lock, keyed by download_key, so they never race on the same fetch.
    key = entry.download_key or entry.name
    lock_path = root / f"{key}.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if dest.exists():
            return dest
        archive_path = root / f"{key}.rar"
        extract_dir = root / f".{key}.extract"
        if not archive_path.exists():
            _download(entry.url, archive_path)
        try:
            shutil.rmtree(extract_dir, ignore_errors=True)
            _run_unar(archive_path, extract_dir)
            _convert_to_geotiff(extract_dir, dest, entry.epsg, entry.member)
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)
        if entry.member is None:
            # Only the already-downloaded archive survives a failed extract/
            # convert (kept so a retry doesn't re-download); it is redundant
            # once the GeoTIFF is safely in place. A split archive's shared
            # download is kept until both siblings are built.
            archive_path.unlink(missing_ok=True)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; ALOS PALSAR mosaics persist in the cache,
    keyed by which region archive covers ``bbox`` (one archive per chunk
    request, so ``tiles_dir`` is unused). Returns an empty list for a chunk
    with no matching archive - a real gap (typically just over the border
    into Argentina), not a fetch failure - so it resolves like any other
    no-coverage chunk."""
    if cache_dir is None:
        raise ValueError("alos_palsar source requires cache_dir")
    entry = _match_archive(bbox, crs)
    if entry is None:
        return []
    return [_ensure_region_geotiff(entry, Path(cache_dir))]
