"""Tests for the ocean/coastline nodata-fill used by every country's chunk raster."""
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from affine import Affine
from shapely.geometry import Polygon, box

from highliner.etls.chunk import ocean
from highliner.models.raster import Raster


def _raster(data: list[list[float]]) -> Raster:
    arr = np.array(data, dtype="float32")
    transform = Affine(1.0, 0, 0, 0, -1.0, arr.shape[0])
    return Raster(data=arr, transform=transform, res=1.0)


def test_fill_ocean_nodata_fills_nan_inside_ocean_polygon() -> None:
    raster = _raster([
        [10.0, 10.0, np.nan, np.nan],
        [10.0, 10.0, np.nan, np.nan],
        [10.0, 10.0, np.nan, np.nan],
        [10.0, 10.0, np.nan, np.nan],
    ])
    ocean_geom = box(2.0, 0.0, 4.0, 4.0)   # right half of the grid (cols 2-3)

    ocean.fill_ocean_nodata(raster, ocean_geom)

    assert np.array_equal(raster.data[:, :2], np.full((4, 2), 10.0, dtype="float32"))
    assert np.array_equal(raster.data[:, 2:], np.zeros((4, 2), dtype="float32"))


def test_fill_ocean_nodata_leaves_nan_outside_ocean_polygon_untouched() -> None:
    raster = _raster([
        [10.0, np.nan, 10.0, 10.0],
        [10.0, np.nan, 10.0, 10.0],
        [10.0, np.nan, 10.0, 10.0],
        [10.0, np.nan, 10.0, 10.0],
    ])
    ocean_geom = box(2.0, 0.0, 4.0, 4.0)   # doesn't cover column 1 (a real void)

    ocean.fill_ocean_nodata(raster, ocean_geom)

    assert np.isnan(raster.data[:, 1]).all()


def test_fill_ocean_nodata_never_overwrites_real_elevation() -> None:
    raster = _raster([[55.0] * 4] * 4)      # no NaN anywhere
    ocean_geom = box(0.0, 0.0, 4.0, 4.0)    # covers the entire grid

    ocean.fill_ocean_nodata(raster, ocean_geom)

    assert np.array_equal(raster.data, np.full((4, 4), 55.0, dtype="float32"))


def _write_ocean_fixture(path: Path) -> None:
    """A small square 'ocean' polygon in WGS84, written as a shapefile —
    same format Natural Earth ships (a directory of .shp/.shx/.dbf/etc)."""
    gdf = gpd.GeoDataFrame(
        {"name": ["test ocean"]},
        geometry=[Polygon([(-72.0, -34.0), (-70.0, -34.0),
                           (-70.0, -32.0), (-72.0, -32.0)])],
        crs="EPSG:4326")
    gdf.to_file(path)


def test_load_ocean_geometry_reprojects_from_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "ne_10m_ocean.shp"
    _write_ocean_fixture(fixture)

    geom = ocean.load_ocean_geometry("EPSG:32719", source_path=fixture)

    # UTM 19S covers this part of Chile; reprojected bounds should land in
    # the hundreds-of-km-to-low-millions range, not still look like lon/lat.
    minx, miny, maxx, maxy = geom.bounds
    assert 100_000 < minx < maxx < 900_000
    assert 6_200_000 < miny < maxy < 6_500_000


def test_load_ocean_geometry_clips_to_crs_area_of_use(tmp_path: Path) -> None:
    """Verify that load_ocean_geometry clips to the CRS's area of use,
    excluding geographically distant polygons."""
    fixture = tmp_path / "ne_10m_ocean.shp"

    # Write a fixture with two polygons: one inside Chile's area of use,
    # one far away in Asia. After clipping to EPSG:32719's bounds, only
    # the Chile polygon should be present.
    gdf = gpd.GeoDataFrame(
        {"name": ["chile ocean", "far away"]},
        geometry=[
            Polygon([(-72.0, -34.0), (-70.0, -34.0),
                    (-70.0, -32.0), (-72.0, -32.0)]),  # inside Chile's bounds
            Polygon([(100.0, 40.0), (101.0, 40.0),
                    (101.0, 41.0), (100.0, 41.0)])      # far away in Asia
        ],
        crs="EPSG:4326")
    gdf.to_file(fixture)

    geom = ocean.load_ocean_geometry("EPSG:32719", source_path=fixture)

    # The resulting geometry should NOT extend anywhere near the far-away
    # polygon's reprojected location. Bounds should stay within UTM 19S range.
    minx, miny, maxx, maxy = geom.bounds
    assert 100_000 < minx < maxx < 900_000
    assert 6_200_000 < miny < maxy < 6_500_000


def test_load_ocean_geometry_clips_spanning_polygon(tmp_path: Path) -> None:
    """Verify that load_ocean_geometry performs true geometric clip, not just
    row filtering. Tests the case where a single polygon's bounding box spans
    from South America to Asia — .cx[] (row filter) would return the entire
    feature unclipped, while .clip() (geometric intersection) correctly cuts it
    to the target area."""
    fixture = tmp_path / "ne_10m_ocean.shp"

    # Create a single polygon spanning from lon -72 (Chile) to lon 100 (Asia).
    # This mimics Natural Earth's ocean polygons which are ocean-basin scale,
    # not per-country. The bbox of this polygon overlaps both Chile's area and
    # distant Asia, but we expect only the Chile portion to remain after clip.
    # Latitude bounds are tight around Chile's area of use for EPSG:32719.
    spanning_polygon = Polygon([
        (-72.0, -34.0), (100.0, -34.0), (100.0, -32.0), (-72.0, -32.0)
    ])
    gdf = gpd.GeoDataFrame(
        {"name": ["spanning ocean"]},
        geometry=[spanning_polygon],
        crs="EPSG:4326")
    gdf.to_file(fixture)

    geom = ocean.load_ocean_geometry("EPSG:32719", source_path=fixture)

    # Bounds should be tightly clipped to Chile's area (similar to existing
    # test ranges). If .cx[] were still used (which just filters rows and
    # returns geometry unclipped), bounds would span from roughly -72 to 100
    # in lon, which is absurd for a single UTM zone. With .clip(), bounds
    # stay within Chile's range.
    minx, miny, maxx, maxy = geom.bounds
    assert 100_000 < minx < maxx < 900_000, \
        f"X bounds {minx}-{maxx} outside Chile UTM19S range"
    assert 6_200_000 < miny < maxy < 6_500_000, \
        f"Y bounds {miny}-{maxy} outside Chile UTM19S range"


def test_load_ocean_geometry_raises_when_source_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.shp"
    with pytest.raises(FileNotFoundError, match="etls.chunk.ocean"):
        ocean.load_ocean_geometry("EPSG:32719", source_path=missing)


def test_download_source_skips_when_already_present(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest_dir = tmp_path / "coastline"
    dest_dir.mkdir()
    (dest_dir / "ne_10m_ocean.shp").write_text("already here")

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not re-download an existing source")

    monkeypatch.setattr(ocean, "_download", boom)

    ocean.download_source(dest_dir)


def test_download_source_fetches_and_extracts_when_missing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest_dir = tmp_path / "coastline"

    def fake_download(_url: str, dest: Path) -> None:
        with zipfile.ZipFile(dest, "w") as archive:
            archive.writestr("ne_10m_ocean.shp", b"shp bytes")
            archive.writestr("ne_10m_ocean.dbf", b"dbf bytes")

    monkeypatch.setattr(ocean, "_download", fake_download)

    ocean.download_source(dest_dir)

    assert (dest_dir / "ne_10m_ocean.shp").read_bytes() == b"shp bytes"
    assert (dest_dir / "ne_10m_ocean.dbf").read_bytes() == b"dbf bytes"
    assert not list(dest_dir.glob("*.zip"))
