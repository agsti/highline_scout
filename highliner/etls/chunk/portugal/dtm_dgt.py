"""Fetch DGT's 2 m bare-earth LiDAR terrain tiles for mainland Portugal.

DGT distributes the ``MDT-2m`` GeoTIFF collection through its CDD STAC API.
The collection is open data but the download API requires a free CDD account;
credentials are supplied only at runtime through environment variables. Sheets
are retained in the country cache and reused by every overlapping chunk.
"""
from __future__ import annotations

import math
import os
import time
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests

from highliner.etls.chunk.dtm_core import _bbox_geom_lonlat

CRS = "EPSG:3763"
COLLECTION = "MDT-2m"
_STAC_URL = "https://cdd.dgterritorio.gov.pt/dgt-be/v1/search"
_AUTH_URL = ("https://auth.cdd.dgterritorio.gov.pt/realms/dgterritorio/"
             "protocol/openid-connect/auth")
_MAIN_SITE = "https://cdd.dgterritorio.gov.pt"
_MAX_AREA_KM2 = 200.0
_RETRIES = 4
_Bbox = tuple[float, float, float, float]


class _LoginForm(HTMLParser):
    """Extract Keycloak's login action and hidden form fields."""

    action: str | None

    def __init__(self) -> None:
        super().__init__()
        self.action = None
        self.fields: dict[str, str] = {}
        self._inside = False

    def handle_starttag(self, tag: str,
                        attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("id") == "kc-form-login":
            self.action = values.get("action")
            self._inside = True
        elif tag == "input" and self._inside and values.get("type") == "hidden":
            name = values.get("name")
            if name:
                self.fields[name] = values.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._inside = False


def _credentials() -> tuple[str, str]:
    username = os.environ.get("DGT_CDD_USERNAME", "")
    password = os.environ.get("DGT_CDD_PASSWORD", "")
    if not username or not password:
        raise RuntimeError(
            "DGT_CDD_USERNAME and DGT_CDD_PASSWORD are required; create a free "
            "account at https://cdd.dgterritorio.gov.pt/")
    return username, password


def _session() -> requests.Session:
    username, password = _credentials()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "highliner-finder/0.1",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
    })
    session.get(_MAIN_SITE, timeout=30).raise_for_status()
    response = session.get(_AUTH_URL, params={
        "client_id": "aai-oidc-dgt", "response_type": "code",
        "redirect_uri": f"{_MAIN_SITE}/auth/callback",
        "scope": "openid profile email",
    }, timeout=30)
    response.raise_for_status()
    form = _LoginForm()
    form.feed(response.text)
    if form.action is None:
        raise RuntimeError("DGT CDD login form was not returned")
    login_url = urllib.parse.urljoin(response.url, form.action)
    form.fields.update({"username": username, "password": password})
    response = session.post(login_url, data=form.fields, timeout=30)
    response.raise_for_status()
    probe = session.post(_STAC_URL, json={"bbox": [-9, 38, -8, 39], "limit": 1},
                         timeout=30)
    if probe.status_code != 200:
        raise RuntimeError("DGT CDD authentication failed; check your credentials")
    return session


def _bbox_lonlat(bbox: _Bbox, crs: str) -> _Bbox:
    bounds = _bbox_geom_lonlat(bbox, crs).bounds
    return tuple(float(value) for value in bounds)  # type: ignore[return-value]


def _sub_bboxes(bbox: _Bbox) -> list[_Bbox]:
    minx, miny, maxx, maxy = bbox
    latitude = (miny + maxy) / 2
    width = (maxx - minx) * 111 * math.cos(math.radians(latitude))
    height = (maxy - miny) * 111
    parts_x = max(1, math.ceil(width / math.sqrt(_MAX_AREA_KM2)))
    parts_y = max(1, math.ceil(height / math.sqrt(_MAX_AREA_KM2)))
    return [(minx + x * (maxx - minx) / parts_x,
             miny + y * (maxy - miny) / parts_y,
             minx + (x + 1) * (maxx - minx) / parts_x,
             miny + (y + 1) * (maxy - miny) / parts_y)
            for x in range(parts_x) for y in range(parts_y)]


def _search(session: requests.Session, bbox: _Bbox) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sub_bbox in _sub_bboxes(bbox):
        response = session.post(_STAC_URL, json={
            "bbox": [sub_bbox[0], sub_bbox[1], sub_bbox[2], sub_bbox[3]],
            "collections": [COLLECTION], "limit": 1000,
        }, timeout=60)
        response.raise_for_status()
        out.extend(response.json().get("features", []))
    return out


def _asset(item: dict[str, Any]) -> tuple[str, str]:
    assets = item.get("assets", {})
    for asset in assets.values():
        if isinstance(asset, dict) and isinstance(asset.get("href"), str):
            return str(item["id"]), asset["href"]
    raise RuntimeError(f"DGT STAC item {item.get('id')} has no downloadable asset")


def _download(session: requests.Session, url: str, dest: Path) -> None:
    for attempt in range(_RETRIES):
        try:
            with session.get(url, stream=True, timeout=300) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                if content_type.startswith("text/html"):
                    raise RuntimeError(
                        "DGT CDD download returned HTML; session expired")
                temporary = dest.with_suffix(".part")
                with temporary.open("wb") as handle:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            handle.write(chunk)
                temporary.replace(dest)
                return
        except requests.RequestException:
            if attempt == _RETRIES - 1:
                raise
            time.sleep(2.0 ** attempt)
    raise RuntimeError("unreachable")


def fetch_dgt_mdt(bbox: _Bbox, cache_root: Path, crs: str,
                  session: requests.Session | object | None = None) -> list[Path]:
    """Return DGT MDT-2m cache sheets intersecting ``bbox``."""
    if crs != CRS:
        raise RuntimeError(f"DGT MDT-2m is published in {CRS}, not {crs}")
    client = _session() if session is None else session
    root = Path(cache_root) / "dgt_mdt_2m"
    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for item in _search(client, _bbox_lonlat(bbox, crs)):  # type: ignore[arg-type]
        item_id, url = _asset(item)
        dest = root / f"{item_id}.tiff"
        if not dest.exists():
            _download(client, url, dest)  # type: ignore[arg-type]
        paths.append(dest)
    return sorted(set(paths))


def fetch(bbox: _Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Module-level multiprocessing entry point for the DGT terrain source."""
    del tiles_dir
    if cache_dir is None:
        raise ValueError("DGT MDT-2m requires a persistent cache directory")
    return fetch_dgt_mdt(bbox, cache_dir, crs)
