"""Shared test fixtures' helpers.

Nothing here may be imported by `highliner/` — this is the tests' side of the
line, and the dead-code scan (`just deadcode`) relies on that split to tell
product code apart from code only its own tests keep alive.
"""

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from highliner.core import config, geo
from highliner.etls.chunk.anchors import save_anchors
from highliner.etls.chunk.candidates import save_candidates
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate

# (centre_x, centre_y, anchor_a, anchor_b, candidate) for one facing pair.
Pair = tuple[float, float, Anchor, Anchor, Candidate]


def to_utm(lon: float, lat: float) -> tuple[float, float]:
    """Lon/lat to the project's UTM zone, for writing fixtures in map coords."""
    return geo.from_lonlat_crs(lon, lat, config.UTM_CRS)


def write_region(data_dir: Path, region: str,  # noqa: PLR0913
                 bbox: tuple[float, float, float, float],
                 anchors: list[Anchor], candidates: list[Candidate],
                 chunk_m: float = 10000.0,
                 crs: str | None = None,
                 country: str = "spain") -> None:
    """Write a minimal one-chunk region in the layout the API expects."""
    region_dir = data_dir / country / region
    (region_dir / "anchors").mkdir(parents=True)
    (region_dir / "pairs").mkdir(parents=True)
    grid = {"bbox": list(bbox), "chunk_m": chunk_m}
    if crs is not None:
        grid["crs"] = crs
    (region_dir / "grid.json").write_text(json.dumps(grid))
    save_anchors(anchors, region_dir / "anchors" / "p_0_0.parquet")
    save_candidates(candidates, region_dir / "pairs" / "q_0_0.parquet")


def gap_region(data_dir: Path, region: str = "test") -> None:
    """Write two facing anchors across an 80 m-deep gap."""
    anchor_a = Anchor(
        x=60.0, y=100.0, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    anchor_b = Anchor(
        x=140.0, y=100.0, elev=100.0, sectors=((260.0, 280.0, 60.0),))
    candidate = Candidate(
        a=anchor_a, b=anchor_b, length=80.0, exposure=80.0, height_diff=0.0)
    write_region(
        data_dir, region, (0.0, 0.0, 300.0, 300.0),
        [anchor_a, anchor_b], [candidate])


def facing_pair(lon: float, lat: float) -> Pair:
    """Build two facing anchors centred on a projected lon/lat point."""
    center_x, center_y = to_utm(lon, lat)
    anchor_a = Anchor(
        x=center_x - 40, y=center_y, elev=100.0,
        sectors=((80.0, 100.0, 60.0),))
    anchor_b = Anchor(
        x=center_x + 40, y=center_y, elev=100.0,
        sectors=((260.0, 280.0, 60.0),))
    candidate = Candidate(
        a=anchor_a, b=anchor_b, length=80.0, exposure=80.0, height_diff=0.0)
    return center_x, center_y, anchor_a, anchor_b, candidate


def write_restriction_layer(
        data_dir: Path, layer_id: str, name: str,
        lonlat_box: tuple[float, float, float, float],
        country: str = "spain") -> None:
    """Write a one-polygon restriction layer in lon/lat coordinates."""
    restriction_dir = data_dir / country / "restrictions"
    restriction_dir.mkdir(parents=True, exist_ok=True)
    west, south, east, north = lonlat_box
    frame = gpd.GeoDataFrame(
        {"name": [name]}, geometry=[box(west, south, east, north)],
        crs="EPSG:4326")
    frame.to_parquet(restriction_dir / f"{layer_id}.parquet")
