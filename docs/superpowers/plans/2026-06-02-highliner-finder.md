# Highliner Finder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tool that discovers candidate highline spots in Catalonia from ICGC LIDAR terrain data: an offline pipeline that extracts sparse cliff "anchor points", plus an interactive Leaflet map that pairs anchors live with adjustable sliders.

**Architecture:** Offline CLI ingests ICGC DTM tiles and extracts directional-drop anchor points into a per-region GeoParquet store. A FastAPI server loads anchors into memory (KDTree) and, per map viewport + slider values, pairs anchors on-the-fly (directional gate + exposure check against the cached DTM) and returns GeoJSON candidate lines drawn by a vanilla-JS Leaflet frontend.

**Tech Stack:** Python (`fastapi`, `uvicorn`, `rasterio`, `numpy`, `scipy`, `pyproj`, `shapely`, `geopandas`/`pyarrow`, `requests`), Leaflet + vanilla JS.

**Spec:** `docs/superpowers/specs/2026-06-02-highliner-finder-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | Package metadata + dependencies |
| `highliner/__init__.py` | Package marker, version |
| `highliner/config.py` | Default parameters (slope, radius, azimuths, CRS constants), data paths |
| `highliner/geo.py` | CRS transforms, bearings, angular-sector test |
| `highliner/raster.py` | `Raster` wrapper: array + affine + nodata; point/line sampling |
| `highliner/terrain.py` | Slope, directional drop sectors, anchor extraction + thinning |
| `highliner/anchors.py` | `Anchor` dataclass + GeoParquet read/write |
| `highliner/ingest.py` | ICGC DTM tile fetch + local mosaic/VRT |
| `highliner/pairing.py` | KDTree pairing, directional gate, exposure, slider filters |
| `highliner/scoring.py` | Candidate quality score + GeoJSON serialization |
| `highliner/api.py` | FastAPI app: `/regions`, `/candidates` |
| `highliner/cli.py` | `ingest` / `analyze` / `serve` commands |
| `web/index.html` | Map page + sliders |
| `web/app.js` | Leaflet map, fetch candidates, draw lines |
| `web/style.css` | Layout/styling |
| `tests/` | Unit + integration tests, synthetic-DTM fixtures |

**Shared data contracts (defined once, used everywhere):**

```python
# highliner/anchors.py
@dataclass(frozen=True)
class Anchor:
    x: float            # UTM 31N (EPSG:25831) easting, meters
    y: float            # UTM 31N northing, meters
    elev: float         # meters
    sectors: tuple[tuple[float, float, float], ...]  # (start_deg, end_deg, max_drop_m)
```

```python
# highliner/raster.py
@dataclass
class Raster:
    data: np.ndarray        # 2D float32, NaN = nodata
    transform: Affine       # rasterio affine (pixel -> UTM)
    res: float              # pixel size in meters (square pixels assumed)
    # crs is always EPSG:25831 for this project
```

GeoParquet anchor columns: `geometry` (Point, EPSG:25831), `elev` (float), `sectors` (JSON string of the sector list).

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `highliner/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/test_smoke.py`:
```python
def test_version():
    import highliner
    assert highliner.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner'`

- [ ] **Step 3: Create package + config files**

`pyproject.toml`:
```toml
[project]
name = "highliner"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "numpy",
    "scipy",
    "rasterio",
    "pyproj",
    "shapely",
    "geopandas",
    "pyarrow",
    "requests",
    "fastapi",
    "uvicorn[standard]",
]

[project.optional-dependencies]
dev = ["pytest", "httpx"]

[project.scripts]
highliner = "highliner.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["highliner*"]
```

`highliner/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`: (empty file)

- [ ] **Step 4: Install editable + run test**

Run: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && python -m pytest tests/test_smoke.py -v`
Expected: PASS. (If geospatial wheels fail on a very new Python, pin Python to 3.11–3.12 in the venv.)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml highliner/__init__.py tests/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold highliner package"
```

---

## Task 2: Config constants

**Files:**
- Create: `highliner/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
from highliner import config

def test_crs_constants():
    assert config.UTM_CRS == "EPSG:25831"
    assert config.WGS84_CRS == "EPSG:4326"

def test_defaults_are_sane():
    assert 40 <= config.SLOPE_MIN_DEG <= 80
    assert config.DROP_RADIUS_M > 0
    assert config.N_AZIMUTHS >= 8
    assert config.DATA_DIR.name == "data"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.config'`

- [ ] **Step 3: Implement**

`highliner/config.py`:
```python
from pathlib import Path

# Coordinate reference systems
UTM_CRS = "EPSG:25831"      # ETRS89 / UTM zone 31N — ICGC native, meters
WGS84_CRS = "EPSG:4326"     # lon/lat for the web map

# Anchor extraction defaults (tunable)
SLOPE_MIN_DEG = 55.0        # cells steeper than this are candidate cliff cells
DROP_RADIUS_M = 25.0        # radius to measure local elevation drop
N_AZIMUTHS = 24             # azimuth samples for the directional sweep (15deg)
MIN_SECTOR_DROP_M = 15.0    # min drop for an azimuth to count as "dropping"
THIN_DIST_M = 15.0          # non-max-suppression spacing between kept anchors

# Pairing defaults (also exposed as sliders)
DEFAULT_MAX_LEN_M = 150.0
DEFAULT_MIN_LEN_M = 20.0
DEFAULT_MIN_EXPOSURE_M = 30.0
DEFAULT_MAX_DH_M = 10.0
SECTOR_TOL_DEG = 10.0       # angular tolerance when testing bearing-in-sector
MAX_CANDIDATES = 500        # cap returned per viewport

# Paths
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/config.py tests/test_config.py
git commit -m "feat: add config constants"
```

---

## Task 3: Geo helpers — bearings & sector test

**Files:**
- Create: `highliner/geo.py`
- Test: `tests/test_geo.py`

- [ ] **Step 1: Write the failing test**

`tests/test_geo.py`:
```python
import math
from highliner import geo

def test_bearing_cardinals():
    # bearing measured clockwise from north (0=N, 90=E, 180=S, 270=W)
    assert geo.bearing(0, 0, 0, 10) == 0       # due north
    assert geo.bearing(0, 0, 10, 0) == 90      # due east
    assert geo.bearing(0, 0, 0, -10) == 180    # due south
    assert geo.bearing(0, 0, -10, 0) == 270    # due west

def test_bearing_in_sector_simple():
    sectors = ((80.0, 100.0, 30.0),)  # faces east
    assert geo.bearing_in_sectors(90, sectors, tol=10)
    assert not geo.bearing_in_sectors(200, sectors, tol=10)

def test_bearing_in_sector_wraps_north():
    sectors = ((350.0, 10.0, 30.0),)  # straddles 0/360
    assert geo.bearing_in_sectors(0, sectors, tol=0)
    assert geo.bearing_in_sectors(355, sectors, tol=0)
    assert not geo.bearing_in_sectors(180, sectors, tol=0)

def test_roundtrip_crs():
    # A point near Montserrat, Catalonia
    lon, lat = 1.83, 41.59
    x, y = geo.to_utm(lon, lat)
    lon2, lat2 = geo.to_lonlat(x, y)
    assert math.isclose(lon, lon2, abs_tol=1e-6)
    assert math.isclose(lat, lat2, abs_tol=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_geo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.geo'`

- [ ] **Step 3: Implement**

`highliner/geo.py`:
```python
import math
from functools import lru_cache
from pyproj import Transformer
from highliner import config


@lru_cache(maxsize=2)
def _transformer(src: str, dst: str) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def to_lonlat(x: float, y: float) -> tuple[float, float]:
    return _transformer(config.UTM_CRS, config.WGS84_CRS).transform(x, y)


def to_utm(lon: float, lat: float) -> tuple[float, float]:
    return _transformer(config.WGS84_CRS, config.UTM_CRS).transform(lon, lat)


def bearing(x1: float, y1: float, x2: float, y2: float) -> float:
    """Clockwise bearing from north, degrees in [0, 360)."""
    deg = math.degrees(math.atan2(x2 - x1, y2 - y1))
    return deg % 360.0


def _angular_contains(start: float, end: float, angle: float) -> bool:
    """Is `angle` within the clockwise arc start->end (handles 0/360 wrap)?"""
    start %= 360.0
    end %= 360.0
    angle %= 360.0
    if start <= end:
        return start <= angle <= end
    return angle >= start or angle <= end


def bearing_in_sectors(angle: float, sectors, tol: float = 0.0) -> bool:
    for start, end, _drop in sectors:
        if _angular_contains(start - tol, end + tol, angle):
            return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_geo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/geo.py tests/test_geo.py
git commit -m "feat: add geo bearing + CRS helpers"
```

---

## Task 4: Raster wrapper — point & line sampling

**Files:**
- Create: `highliner/raster.py`
- Test: `tests/test_raster.py`

- [ ] **Step 1: Write the failing test**

`tests/test_raster.py`:
```python
import numpy as np
from affine import Affine
from highliner.raster import Raster

def make_raster():
    # 10x10 grid, 1m pixels, origin at (0, 10) top-left, y decreasing downward.
    # value = elevation = x_index (column) so it ramps west->east.
    data = np.tile(np.arange(10, dtype="float32"), (10, 1))
    transform = Affine(1.0, 0, 0, 0, -1.0, 10.0)
    return Raster(data=data, transform=transform, res=1.0)

def test_value_at_known_cell():
    r = make_raster()
    # UTM (3.5, 5.5) -> column 3, value 3
    assert r.value_at(3.5, 5.5) == 3.0

def test_value_at_outside_is_nan():
    r = make_raster()
    assert np.isnan(r.value_at(-5, -5))

def test_sample_line_returns_profile():
    r = make_raster()
    # horizontal line west->east at y=5.5 from x=0.5 to x=9.5
    prof = r.sample_line(0.5, 5.5, 9.5, 5.5, step=1.0)
    assert prof[0] == 0.0
    assert prof[-1] == 9.0
    assert np.all(np.diff(prof) >= 0)  # monotonic increasing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_raster.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.raster'`

- [ ] **Step 3: Implement**

`highliner/raster.py`:
```python
from dataclasses import dataclass
import numpy as np
from affine import Affine


@dataclass
class Raster:
    data: np.ndarray      # 2D float, NaN = nodata
    transform: Affine     # pixel -> UTM (EPSG:25831)
    res: float            # meters per pixel (square)

    def _rowcol(self, x: float, y: float) -> tuple[int, int]:
        col, row = ~self.transform * (x, y)
        return int(np.floor(row)), int(np.floor(col))

    def value_at(self, x: float, y: float) -> float:
        row, col = self._rowcol(x, y)
        h, w = self.data.shape
        if 0 <= row < h and 0 <= col < w:
            return float(self.data[row, col])
        return float("nan")

    def sample_line(self, x1, y1, x2, y2, step: float | None = None) -> np.ndarray:
        step = step or self.res
        length = float(np.hypot(x2 - x1, y2 - y1))
        n = max(2, int(length / step) + 1)
        xs = np.linspace(x1, x2, n)
        ys = np.linspace(y1, y2, n)
        return np.array([self.value_at(float(x), float(y)) for x, y in zip(xs, ys)])

    @classmethod
    def open(cls, path) -> "Raster":
        import rasterio
        with rasterio.open(path) as ds:
            arr = ds.read(1).astype("float32")
            if ds.nodata is not None:
                arr[arr == ds.nodata] = np.nan
            return cls(data=arr, transform=ds.transform, res=abs(ds.transform.a))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_raster.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/raster.py tests/test_raster.py
git commit -m "feat: add Raster wrapper with point/line sampling"
```

---

## Task 5: Terrain — slope

**Files:**
- Create: `highliner/terrain.py`
- Test: `tests/test_terrain_slope.py`

- [ ] **Step 1: Write the failing test**

`tests/test_terrain_slope.py`:
```python
import numpy as np
from highliner import terrain

def test_flat_is_zero_slope():
    dtm = np.full((5, 5), 100.0, dtype="float32")
    slope = terrain.compute_slope(dtm, res=1.0)
    assert np.allclose(slope, 0.0)

def test_45_degree_ramp():
    # rise 1m per 1m horizontally => 45 degrees
    dtm = np.tile(np.arange(5, dtype="float32"), (5, 1))
    slope = terrain.compute_slope(dtm, res=1.0)
    # interior cells should be ~45 degrees
    assert np.isclose(slope[2, 2], 45.0, atol=1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_terrain_slope.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError: module has no attribute 'compute_slope'`

- [ ] **Step 3: Implement**

`highliner/terrain.py`:
```python
import numpy as np


def compute_slope(dtm: np.ndarray, res: float) -> np.ndarray:
    """Slope in degrees from an elevation grid (np.gradient based)."""
    dy, dx = np.gradient(dtm, res)
    rise = np.hypot(dx, dy)
    return np.degrees(np.arctan(rise))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_terrain_slope.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/terrain.py tests/test_terrain_slope.py
git commit -m "feat: add slope computation"
```

---

## Task 6: Terrain — directional drop sectors

**Files:**
- Modify: `highliner/terrain.py`
- Test: `tests/test_terrain_sectors.py`

- [ ] **Step 1: Write the failing test**

`tests/test_terrain_sectors.py`:
```python
import numpy as np
from affine import Affine
from highliner.raster import Raster
from highliner import terrain

def cliff_raster():
    # 41x41, 1m pixels. Flat plateau at 100m for x<20, drops to 50m for x>=20.
    # An anchor at the rim (x=19) should "drop" toward the EAST (bearing 90).
    data = np.full((41, 41), 100.0, dtype="float32")
    data[:, 20:] = 50.0
    transform = Affine(1.0, 0, 0, 0, -1.0, 41.0)
    return Raster(data=data, transform=transform, res=1.0)

def test_sectors_face_the_drop():
    r = cliff_raster()
    # point on the plateau just west of the edge, center row
    x, y = 19.5, 20.5
    sectors = terrain.drop_sectors(r, x, y, radius=15.0, n_azimuths=24,
                                   min_drop=15.0)
    assert sectors, "expected at least one dropping sector"
    # at least one sector must contain due-east (90 deg)
    from highliner.geo import bearing_in_sectors
    assert bearing_in_sectors(90, sectors, tol=0)
    # and none should contain due-west (270): plateau is flat that way
    assert not bearing_in_sectors(270, sectors, tol=0)

def test_flat_has_no_sectors():
    data = np.full((41, 41), 100.0, dtype="float32")
    r = Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 41.0), res=1.0)
    assert terrain.drop_sectors(r, 20.5, 20.5, radius=15.0, n_azimuths=24,
                                min_drop=15.0) == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_terrain_sectors.py -v`
Expected: FAIL — `AttributeError: module 'highliner.terrain' has no attribute 'drop_sectors'`

- [ ] **Step 3: Implement**

Append to `highliner/terrain.py`:
```python
import math
from highliner.raster import Raster


def drop_sectors(raster: Raster, x: float, y: float, radius: float,
                 n_azimuths: int, min_drop: float):
    """Sweep azimuths around (x, y); group consecutive dropping directions
    into sectors. Returns tuple of (start_deg, end_deg, max_drop)."""
    base = raster.value_at(x, y)
    if math.isnan(base):
        return ()
    step_deg = 360.0 / n_azimuths
    drops = []  # (azimuth, drop) for every sampled direction
    for i in range(n_azimuths):
        az = i * step_deg
        rad = math.radians(az)
        # bearing: 0=N(+y), 90=E(+x)
        tx = x + radius * math.sin(rad)
        ty = y + radius * math.cos(rad)
        far = raster.value_at(tx, ty)
        drop = 0.0 if math.isnan(far) else base - far
        drops.append((az, drop))

    dropping = [(az, d) for az, d in drops if d >= min_drop]
    if not dropping:
        return ()

    # group consecutive azimuths (circularly) into sectors
    flags = [d >= min_drop for _, d in drops]
    sectors = []
    n = n_azimuths
    visited = [False] * n
    for start in range(n):
        if not flags[start] or visited[start]:
            continue
        # only start a run at a rising edge (previous is False) to avoid splits
        if flags[(start - 1) % n]:
            continue
        j = start
        max_drop = 0.0
        while flags[j % n] and not visited[j % n]:
            visited[j % n] = True
            max_drop = max(max_drop, drops[j % n][1])
            j += 1
        sectors.append((drops[start][0],
                        drops[(j - 1) % n][0],
                        round(max_drop, 2)))
    # if the whole circle drops (all flags true) emit one full sector
    if all(flags) and not sectors:
        md = round(max(d for _, d in drops), 2)
        sectors.append((0.0, 360.0 - step_deg, md))
    return tuple(sectors)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_terrain_sectors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/terrain.py tests/test_terrain_sectors.py
git commit -m "feat: add directional drop sectors"
```

---

## Task 7: Anchors — dataclass + GeoParquet I/O

**Files:**
- Create: `highliner/anchors.py`
- Test: `tests/test_anchors.py`

- [ ] **Step 1: Write the failing test**

`tests/test_anchors.py`:
```python
from highliner.anchors import Anchor, save_anchors, load_anchors

def test_roundtrip(tmp_path):
    anchors = [
        Anchor(x=100.0, y=200.0, elev=540.5, sectors=((80.0, 100.0, 35.0),)),
        Anchor(x=150.0, y=210.0, elev=541.0,
               sectors=((250.0, 280.0, 40.0), (10.0, 30.0, 20.0))),
    ]
    path = tmp_path / "anchors.parquet"
    save_anchors(anchors, path)
    loaded = load_anchors(path)
    assert len(loaded) == 2
    assert loaded[0].sectors == ((80.0, 100.0, 35.0),)
    assert loaded[1].x == 150.0
    assert loaded[1].sectors[0] == (250.0, 280.0, 40.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_anchors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.anchors'`

- [ ] **Step 3: Implement**

`highliner/anchors.py`:
```python
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Anchor:
    x: float
    y: float
    elev: float
    sectors: tuple  # ((start_deg, end_deg, max_drop), ...)


def save_anchors(anchors, path):
    import geopandas as gpd
    from shapely.geometry import Point
    from highliner import config
    rows = {
        "geometry": [Point(a.x, a.y) for a in anchors],
        "elev": [a.elev for a in anchors],
        "sectors": [json.dumps([list(s) for s in a.sectors]) for a in anchors],
    }
    gdf = gpd.GeoDataFrame(rows, crs=config.UTM_CRS)
    gdf.to_parquet(path)


def load_anchors(path) -> list[Anchor]:
    import geopandas as gpd
    gdf = gpd.read_parquet(path)
    out = []
    for geom, elev, sectors in zip(gdf.geometry, gdf.elev, gdf.sectors):
        secs = tuple(tuple(s) for s in json.loads(sectors))
        out.append(Anchor(x=geom.x, y=geom.y, elev=float(elev), sectors=secs))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_anchors.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/anchors.py tests/test_anchors.py
git commit -m "feat: add Anchor dataclass + GeoParquet I/O"
```

---

## Task 8: Terrain — extract & thin anchors from a Raster

**Files:**
- Modify: `highliner/terrain.py`
- Test: `tests/test_terrain_extract.py`

- [ ] **Step 1: Write the failing test**

`tests/test_terrain_extract.py`:
```python
import numpy as np
from affine import Affine
from highliner.raster import Raster
from highliner import terrain

def two_sided_cliff():
    # 61x61, plateau 100m in a central band x in [28,32], drops to 40m either side
    data = np.full((61, 61), 40.0, dtype="float32")
    data[:, 28:33] = 100.0
    return Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 61.0), res=1.0)

def test_extract_finds_rim_anchors():
    r = two_sided_cliff()
    anchors = terrain.extract_anchors(
        r, slope_min=40.0, radius=15.0, n_azimuths=24,
        min_sector_drop=15.0, thin_dist=10.0)
    assert anchors, "expected anchors along the plateau rim"
    # every anchor sits on the high band (elev ~100) and has >=1 sector
    for a in anchors:
        assert a.elev > 90
        assert len(a.sectors) >= 1

def test_thinning_limits_density():
    r = two_sided_cliff()
    dense = terrain.extract_anchors(r, 40.0, 15.0, 24, 15.0, thin_dist=2.0)
    sparse = terrain.extract_anchors(r, 40.0, 15.0, 24, 15.0, thin_dist=20.0)
    assert len(sparse) < len(dense)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_terrain_extract.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'extract_anchors'`

- [ ] **Step 3: Implement**

Append to `highliner/terrain.py`:
```python
from highliner.anchors import Anchor


def _thin(points, thin_dist):
    """Greedy non-max suppression by descending drop; keep points >= thin_dist apart."""
    from scipy.spatial import cKDTree
    if not points:
        return []
    pts = sorted(points, key=lambda p: -p[4])  # p = (x, y, elev, sectors, score)
    kept = []
    kept_xy = []
    tree = None
    for x, y, elev, sectors, _score in pts:
        if kept_xy:
            tree = cKDTree(kept_xy)
            if tree.query_ball_point([x, y], thin_dist):
                continue
        kept.append(Anchor(x=x, y=y, elev=elev, sectors=sectors))
        kept_xy.append([x, y])
    return kept


def extract_anchors(raster: Raster, slope_min: float, radius: float,
                    n_azimuths: int, min_sector_drop: float,
                    thin_dist: float) -> list[Anchor]:
    slope = compute_slope(raster.data, raster.res)
    steep = np.argwhere(slope >= slope_min)
    candidates = []
    for row, col in steep:
        x, y = raster.transform * (col + 0.5, row + 0.5)
        sectors = drop_sectors(raster, x, y, radius, n_azimuths, min_sector_drop)
        if not sectors:
            continue
        elev = raster.value_at(x, y)
        if np.isnan(elev):
            continue
        best_drop = max(s[2] for s in sectors)
        candidates.append((x, y, float(elev), sectors, best_drop))
    return _thin(candidates, thin_dist)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_terrain_extract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/terrain.py tests/test_terrain_extract.py
git commit -m "feat: extract and thin anchors from raster"
```

---

## Task 9: Pairing — neighbor query + filters + directional gate + exposure

**Files:**
- Create: `highliner/pairing.py`
- Test: `tests/test_pairing.py`

- [ ] **Step 1: Write the failing test**

`tests/test_pairing.py`:
```python
import numpy as np
from affine import Affine
from highliner.raster import Raster
from highliner.anchors import Anchor
from highliner import pairing

def gap_raster():
    # plateau 100m at x<=30 and x>=70, deep gap (20m) in the middle.
    data = np.full((101, 101), 100.0, dtype="float32")
    data[:, 31:70] = 20.0
    return Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 101.0), res=1.0)

def facing_pair():
    # west rim anchor faces east (90); east rim anchor faces west (270)
    a = Anchor(x=30.0, y=50.0, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    b = Anchor(x=70.0, y=50.0, elev=100.0, sectors=((260.0, 280.0, 60.0),))
    return a, b

def test_facing_pair_across_gap_is_found():
    r = gap_raster()
    a, b = facing_pair()
    res = pairing.find_candidates([a, b], r, max_len=60, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert len(res) == 1
    c = res[0]
    assert abs(c.length - 40.0) < 1.5
    assert c.exposure >= 50

def test_rejected_when_too_long():
    r = gap_raster()
    a, b = facing_pair()
    res = pairing.find_candidates([a, b], r, max_len=30, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert res == []

def test_rejected_when_not_facing():
    r = gap_raster()
    a, b = facing_pair()
    b_wrong = Anchor(x=70.0, y=50.0, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    res = pairing.find_candidates([a, b_wrong], r, max_len=60, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert res == []

def test_rejected_when_height_diff_too_big():
    r = gap_raster()
    a, b = facing_pair()
    b_high = Anchor(x=70.0, y=50.0, elev=140.0, sectors=((260.0, 280.0, 60.0),))
    res = pairing.find_candidates([a, b_high], r, max_len=60, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert res == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pairing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.pairing'`

- [ ] **Step 3: Implement**

`highliner/pairing.py`:
```python
from dataclasses import dataclass
import numpy as np
from scipy.spatial import cKDTree
from highliner import config, geo
from highliner.raster import Raster
from highliner.anchors import Anchor


@dataclass(frozen=True)
class Candidate:
    a: Anchor
    b: Anchor
    length: float
    exposure: float
    height_diff: float


def _interior_min(profile: np.ndarray) -> float:
    """Lowest value strictly inside the profile (exclude the two endpoints)."""
    if profile.size <= 2:
        return float("nan")
    interior = profile[1:-1]
    interior = interior[~np.isnan(interior)]
    return float(np.min(interior)) if interior.size else float("nan")


def find_candidates(anchors, raster: Raster, max_len, min_len,
                    min_exposure, max_dh, sector_tol=config.SECTOR_TOL_DEG):
    if len(anchors) < 2:
        return []
    coords = np.array([[a.x, a.y] for a in anchors])
    tree = cKDTree(coords)
    seen = set()
    out = []
    for i, a in enumerate(anchors):
        for j in tree.query_ball_point(coords[i], max_len):
            if j <= i:
                continue
            b = anchors[j]
            key = (i, j)
            if key in seen:
                continue
            seen.add(key)

            length = float(np.hypot(b.x - a.x, b.y - a.y))
            if length < min_len or length > max_len:
                continue

            dh = abs(a.elev - b.elev)
            if dh > max_dh:
                continue

            ab = geo.bearing(a.x, a.y, b.x, b.y)
            ba = (ab + 180.0) % 360.0
            if not geo.bearing_in_sectors(ab, a.sectors, sector_tol):
                continue
            if not geo.bearing_in_sectors(ba, b.sectors, sector_tol):
                continue

            profile = raster.sample_line(a.x, a.y, b.x, b.y)
            low = _interior_min(profile)
            if np.isnan(low):
                continue
            exposure = min(a.elev, b.elev) - low
            if exposure < min_exposure:
                continue

            out.append(Candidate(a=a, b=b, length=round(length, 1),
                                 exposure=round(exposure, 1),
                                 height_diff=round(dh, 1)))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pairing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/pairing.py tests/test_pairing.py
git commit -m "feat: add anchor pairing with directional gate + exposure"
```

---

## Task 10: Scoring + GeoJSON serialization

**Files:**
- Create: `highliner/scoring.py`
- Test: `tests/test_scoring.py`

- [ ] **Step 1: Write the failing test**

`tests/test_scoring.py`:
```python
from highliner.anchors import Anchor
from highliner.pairing import Candidate
from highliner import scoring

def make_cand(exposure, dh, length):
    a = Anchor(0, 0, 100, ((80, 100, 60),))
    b = Anchor(length, 0, 100 - dh, ((260, 280, 60),))
    return Candidate(a=a, b=b, length=length, exposure=exposure, height_diff=dh)

def test_more_exposure_scores_higher():
    low = make_cand(30, 0, 50)
    high = make_cand(80, 0, 50)
    assert scoring.score(high) > scoring.score(low)

def test_geojson_structure():
    fc = scoring.to_geojson([make_cand(50, 2, 40)])
    assert fc["type"] == "FeatureCollection"
    feat = fc["features"][0]
    assert feat["geometry"]["type"] == "LineString"
    assert len(feat["geometry"]["coordinates"]) == 2
    props = feat["properties"]
    assert {"length", "exposure", "height_diff", "score"} <= props.keys()
    # coordinates are lon/lat (roughly within Catalonia / valid lon-lat range)
    for lon, lat in feat["geometry"]["coordinates"]:
        assert -180 <= lon <= 180 and -90 <= lat <= 90
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.scoring'`

- [ ] **Step 3: Implement**

`highliner/scoring.py`:
```python
from highliner import geo
from highliner.pairing import Candidate


def score(c: Candidate) -> float:
    """Higher = better. Reward exposure, penalize height difference."""
    return round(c.exposure - 2.0 * c.height_diff, 2)


def to_geojson(candidates) -> dict:
    features = []
    for c in sorted(candidates, key=score, reverse=True):
        a_lon, a_lat = geo.to_lonlat(c.a.x, c.a.y)
        b_lon, b_lat = geo.to_lonlat(c.b.x, c.b.y)
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[a_lon, a_lat], [b_lon, b_lat]],
            },
            "properties": {
                "length": c.length,
                "exposure": c.exposure,
                "height_diff": c.height_diff,
                "score": score(c),
            },
        })
    return {"type": "FeatureCollection", "features": features}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scoring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/scoring.py tests/test_scoring.py
git commit -m "feat: add candidate scoring + GeoJSON output"
```

---

## Task 11: Ingest — ICGC DTM fetch + mosaic

ICGC publishes a 2m DTM ("MET2") as downloadable raster tiles and via WCS/WMS.
This task implements a fetch-by-bbox that downloads the covering tile(s) via the
ICGC WCS (GeoTIFF), caches them, and exposes the path. The network call is
wrapped so tests can mock it.

**Files:**
- Create: `highliner/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test**

`tests/test_ingest.py`:
```python
import numpy as np
import rasterio
from rasterio.transform import from_origin
from highliner import ingest

def _write_tif(path):
    data = np.tile(np.arange(20, dtype="float32"), (20, 1))
    transform = from_origin(420000, 4600020, 2.0, 2.0)
    with rasterio.open(path, "w", driver="GTiff", height=20, width=20,
                       count=1, dtype="float32", crs="EPSG:25831",
                       transform=transform) as ds:
        ds.write(data, 1)

def test_fetch_caches_and_returns_path(tmp_path, monkeypatch):
    calls = []
    def fake_download(bbox, dest):
        calls.append(bbox)
        _write_tif(dest)
        return dest
    monkeypatch.setattr(ingest, "_download_dtm", fake_download)

    bbox = (420000, 4600000, 420040, 4600040)
    p1 = ingest.fetch_dtm(bbox, region="test", data_dir=tmp_path)
    assert p1.exists()
    # second call hits cache, no new download
    p2 = ingest.fetch_dtm(bbox, region="test", data_dir=tmp_path)
    assert p1 == p2
    assert len(calls) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.ingest'`

- [ ] **Step 3: Implement**

`highliner/ingest.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/ingest.py tests/test_ingest.py
git commit -m "feat: add ICGC DTM fetch with caching"
```

> **Manual verification note (not a blocker):** During execution, do one real
> `fetch_dtm` against a small known Catalan bbox to confirm `COVERAGE_ID` and the
> WCS axis labels (`E`/`N`) are correct; fix the coverage id/axis names if ICGC's
> capabilities differ. Document the working values in `highliner/ingest.py`.

---

## Task 12: API — /regions and /candidates

**Files:**
- Create: `highliner/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

`tests/test_api.py`:
```python
import numpy as np
from affine import Affine
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from highliner.anchors import Anchor, save_anchors
from highliner import api

def _setup_region(data_dir):
    region = data_dir / "test"
    region.mkdir(parents=True)
    # DTM: plateau 100 with a gap (20) between x cols 31..69 (2m px from origin)
    data = np.full((101, 101), 100.0, dtype="float32")
    data[:, 31:70] = 20.0
    transform = from_origin(0, 202, 2.0, 2.0)
    with rasterio.open(region / "mosaic.tif", "w", driver="GTiff",
                       height=101, width=101, count=1, dtype="float32",
                       crs="EPSG:25831", transform=transform) as ds:
        ds.write(data, 1)
    # two facing anchors across the gap (UTM coords)
    a = Anchor(x=60.0, y=100.0, elev=100.0, sectors=((80, 100, 60),))
    b = Anchor(x=140.0, y=100.0, elev=100.0, sectors=((260, 280, 60),))
    save_anchors([a, b], region / "anchors.parquet")

def test_candidates_endpoint(tmp_path):
    _setup_region(tmp_path)
    app = api.create_app(data_dir=tmp_path)
    client = TestClient(app)

    assert "test" in client.get("/regions").json()["regions"]

    r = client.get("/candidates", params={
        "region": "test",
        "bbox": "0,0,300,300",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.api'`

- [ ] **Step 3: Implement**

`highliner/api.py`:
```python
from pathlib import Path
from functools import lru_cache
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from highliner import config, scoring
from highliner.anchors import load_anchors
from highliner.raster import Raster
from highliner.pairing import find_candidates


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir or config.DATA_DIR)
    app = FastAPI(title="Highliner Finder")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    @lru_cache(maxsize=8)
    def _region(region: str):
        rdir = data_dir / region
        apath = rdir / "anchors.parquet"
        mpath = rdir / "mosaic.tif"
        if not apath.exists() or not mpath.exists():
            raise HTTPException(404, f"region '{region}' not found")
        return load_anchors(apath), Raster.open(mpath)

    @app.get("/regions")
    def regions():
        if not data_dir.exists():
            return {"regions": []}
        names = [p.name for p in data_dir.iterdir()
                 if (p / "anchors.parquet").exists()]
        return {"regions": sorted(names)}

    @app.get("/candidates")
    def candidates(
        region: str,
        bbox: str = Query(..., description="minx,miny,maxx,maxy in EPSG:25831"),
        max_len: float = config.DEFAULT_MAX_LEN_M,
        min_len: float = config.DEFAULT_MIN_LEN_M,
        min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
        max_dh: float = config.DEFAULT_MAX_DH_M,
    ):
        anchors, raster = _region(region)
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
        in_view = [a for a in anchors if minx <= a.x <= maxx and miny <= a.y <= maxy]
        if len(in_view) > 20000:
            raise HTTPException(413, "too many anchors in view; zoom in")
        cands = find_candidates(in_view, raster, max_len, min_len,
                                min_exposure, max_dh)
        cands = sorted(cands, key=scoring.score, reverse=True)[:config.MAX_CANDIDATES]
        return scoring.to_geojson(cands)

    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/api.py tests/test_api.py
git commit -m "feat: add FastAPI regions + candidates endpoints"
```

---

## Task 13: CLI — ingest / analyze / serve

**Files:**
- Create: `highliner/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
import numpy as np
import rasterio
from rasterio.transform import from_origin
from highliner import cli
from highliner.anchors import load_anchors

def test_analyze_writes_anchors(tmp_path, monkeypatch):
    region = tmp_path / "demo"
    region.mkdir()
    # two-sided cliff so anchors exist
    data = np.full((61, 61), 40.0, dtype="float32")
    data[:, 28:33] = 100.0
    with rasterio.open(region / "mosaic.tif", "w", driver="GTiff", height=61,
                       width=61, count=1, dtype="float32", crs="EPSG:25831",
                       transform=from_origin(0, 122, 2.0, 2.0)) as ds:
        ds.write(data, 1)

    cli.main(["analyze", "--region", "demo", "--data-dir", str(tmp_path)])
    anchors = load_anchors(region / "anchors.parquet")
    assert len(anchors) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.cli'`

- [ ] **Step 3: Implement**

`highliner/cli.py`:
```python
import argparse
from pathlib import Path
from highliner import config


def _cmd_ingest(args):
    from highliner.ingest import fetch_dtm
    bbox = tuple(float(v) for v in args.bbox.split(","))
    path = fetch_dtm(bbox, region=args.region, data_dir=Path(args.data_dir))
    # build/refresh the region mosaic as a simple copy/VRT of fetched tiles
    print(f"fetched DTM -> {path}")
    print("note: if multiple tiles, build data/<region>/mosaic.tif via gdalbuildvrt")


def _cmd_analyze(args):
    from highliner.raster import Raster
    from highliner.terrain import extract_anchors
    from highliner.anchors import save_anchors
    rdir = Path(args.data_dir) / args.region
    raster = Raster.open(rdir / "mosaic.tif")
    anchors = extract_anchors(
        raster, slope_min=config.SLOPE_MIN_DEG, radius=config.DROP_RADIUS_M,
        n_azimuths=config.N_AZIMUTHS, min_sector_drop=config.MIN_SECTOR_DROP_M,
        thin_dist=config.THIN_DIST_M)
    out = rdir / "anchors.parquet"
    save_anchors(anchors, out)
    print(f"extracted {len(anchors)} anchors -> {out}")


def _cmd_serve(args):
    import uvicorn
    from highliner.api import create_app
    app = create_app(data_dir=Path(args.data_dir))
    uvicorn.run(app, host=args.host, port=args.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="highliner")
    p.add_argument("--data-dir", default=str(config.DATA_DIR))
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest")
    pi.add_argument("--bbox", required=True, help="minx,miny,maxx,maxy EPSG:25831")
    pi.add_argument("--region", required=True)
    pi.set_defaults(func=_cmd_ingest)

    pa = sub.add_parser("analyze")
    pa.add_argument("--region", required=True)
    pa.set_defaults(func=_cmd_analyze)

    ps = sub.add_parser("serve")
    ps.add_argument("--host", default="127.0.0.1")
    ps.add_argument("--port", type=int, default=8000)
    ps.set_defaults(func=_cmd_serve)

    args = p.parse_args(argv)
    args.func(args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/cli.py tests/test_cli.py
git commit -m "feat: add ingest/analyze/serve CLI"
```

---

## Task 14: Frontend — Leaflet map with sliders

No automated test (static assets). Verified manually against a running server.

**Files:**
- Create: `web/index.html`
- Create: `web/style.css`
- Create: `web/app.js`
- Modify: `highliner/api.py` (mount static files)

- [ ] **Step 1: Mount the web directory in the API**

In `highliner/api.py`, inside `create_app`, before `return app`:
```python
    from fastapi.staticfiles import StaticFiles
    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
```

- [ ] **Step 2: Create `web/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Highliner Finder</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="panel">
    <h1>Highliner Finder</h1>
    <label>Region <select id="region"></select></label>
    <label>Max length <span id="maxLenV">150</span> m
      <input type="range" id="maxLen" min="20" max="500" value="150" /></label>
    <label>Min exposure <span id="minExpV">30</span> m
      <input type="range" id="minExp" min="0" max="300" value="30" /></label>
    <label>Max height diff <span id="maxDhV">10</span> m
      <input type="range" id="maxDh" min="0" max="50" value="10" /></label>
    <p class="caveat">Candidates to scout — not confirmed-riggable. No bolts,
      trees, loose rock, access or permissions are verified.</p>
    <p id="status"></p>
  </div>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create `web/style.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; }
#map { position: absolute; top: 0; left: 320px; right: 0; bottom: 0; }
#panel { position: absolute; top: 0; left: 0; width: 320px; bottom: 0;
  padding: 16px; overflow-y: auto; background: #f7f7f7;
  border-right: 1px solid #ddd; }
#panel h1 { font-size: 18px; }
#panel label { display: block; margin: 12px 0; font-size: 14px; }
#panel input[type=range] { width: 100%; }
.caveat { font-size: 12px; color: #a33; margin-top: 16px; }
#status { font-size: 12px; color: #555; }
```

- [ ] **Step 4: Create `web/app.js`**

```javascript
const map = L.map("map").setView([41.6, 1.83], 13); // Montserrat area
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(map);

let layer = L.geoJSON(null, {
  style: { color: "#e6005c", weight: 3 },
  onEachFeature: (f, l) => {
    const p = f.properties;
    l.bindPopup(`length ${p.length} m<br>exposure ${p.exposure} m<br>`
      + `Δh ${p.height_diff} m<br>score ${p.score}`);
  },
}).addTo(map);

const $ = (id) => document.getElementById(id);
const ctrls = ["maxLen", "minExp", "maxDh"];
ctrls.forEach((id) => $(id).addEventListener("input", () => {
  $(id + "V").textContent = $(id).value;
  refresh();
}));
map.on("moveend", refresh);

// project lon/lat bbox -> EPSG:25831 server-side is simpler; here we send
// lon/lat corners and let the API translate via a /bbox query param in 25831.
// To keep the API simple, we transform on the client using a tiny proj call
// through the backend is avoided: instead the API accepts 25831 only, so we
// convert using the map's known UTM via a helper endpoint is overkill.
// Simplest: request candidates with a lon/lat bbox the API converts. The API
// in this plan expects 25831, so we add a thin conversion below.

async function loadRegions() {
  const r = await fetch("/regions").then((x) => x.json());
  r.regions.forEach((name) => {
    const o = document.createElement("option");
    o.value = o.textContent = name;
    $("region").appendChild(o);
  });
  $("region").addEventListener("change", refresh);
  refresh();
}

async function refresh() {
  const region = $("region").value;
  if (!region) return;
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  const params = new URLSearchParams({
    region, bbox_lonlat: bbox,
    max_len: $("maxLen").value,
    min_exposure: $("minExp").value,
    max_dh: $("maxDh").value,
  });
  $("status").textContent = "searching…";
  try {
    const fc = await fetch("/candidates?" + params).then((x) => x.json());
    layer.clearLayers();
    layer.addData(fc);
    $("status").textContent = `${fc.features.length} candidates`;
  } catch (e) {
    $("status").textContent = "error: " + e;
  }
}
loadRegions();
```

- [ ] **Step 5: Add a lon/lat bbox option to the API**

The frontend sends `bbox_lonlat` (WGS84). Update `/candidates` in
`highliner/api.py` to accept either `bbox` (25831) or `bbox_lonlat` and convert:
```python
    @app.get("/candidates")
    def candidates(
        region: str,
        bbox: str | None = None,
        bbox_lonlat: str | None = None,
        max_len: float = config.DEFAULT_MAX_LEN_M,
        min_len: float = config.DEFAULT_MIN_LEN_M,
        min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
        max_dh: float = config.DEFAULT_MAX_DH_M,
    ):
        from highliner import geo
        anchors, raster = _region(region)
        if bbox_lonlat:
            w, s, e, n = (float(v) for v in bbox_lonlat.split(","))
            minx, miny = geo.to_utm(w, s)
            maxx, maxy = geo.to_utm(e, n)
        elif bbox:
            minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
        else:
            raise HTTPException(400, "provide bbox or bbox_lonlat")
        in_view = [a for a in anchors if minx <= a.x <= maxx and miny <= a.y <= maxy]
        if len(in_view) > 20000:
            raise HTTPException(413, "too many anchors in view; zoom in")
        cands = find_candidates(in_view, raster, max_len, min_len,
                                min_exposure, max_dh)
        cands = sorted(cands, key=scoring.score, reverse=True)[:config.MAX_CANDIDATES]
        return scoring.to_geojson(cands)
```
Update `tests/test_api.py` to keep the existing `bbox` test passing (it still
provides `bbox`), and add one asserting `bbox_lonlat` works for a known region.

- [ ] **Step 6: Run API tests + manual smoke**

Run: `python -m pytest tests/test_api.py -v`
Expected: PASS
Manual: `highliner serve --data-dir data` then open `http://127.0.0.1:8000/`,
confirm the map loads, region appears, sliders update the line count.

- [ ] **Step 7: Commit**

```bash
git add web/ highliner/api.py tests/test_api.py
git commit -m "feat: add Leaflet frontend + lon/lat bbox support"
```

---

## Task 15: End-to-end integration test

**Files:**
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write the failing test**

`tests/test_integration.py`:
```python
import numpy as np
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from highliner import cli, api

def test_full_pipeline(tmp_path):
    region = tmp_path / "demo"
    region.mkdir()
    # plateau 100m with a deep central gap -> two facing rims, one good line
    data = np.full((151, 151), 100.0, dtype="float32")
    data[:, 60:90] = 20.0
    with rasterio.open(region / "mosaic.tif", "w", driver="GTiff", height=151,
                       width=151, count=1, dtype="float32", crs="EPSG:25831",
                       transform=from_origin(420000, 4600302, 2.0, 2.0)) as ds:
        ds.write(data, 1)

    cli.main(["analyze", "--region", "demo", "--data-dir", str(tmp_path)])

    client = TestClient(api.create_app(data_dir=tmp_path))
    fc = client.get("/candidates", params={
        "region": "demo", "bbox": "420000,4600000,420302,4600302",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    }).json()
    assert fc["features"], "expected at least one candidate across the gap"
    best = fc["features"][0]["properties"]
    assert best["exposure"] >= 50
```

- [ ] **Step 2: Run test to verify it fails (or passes if all wired)**

Run: `python -m pytest tests/test_integration.py -v`
Expected: PASS if Tasks 8–13 are correct. If it FAILS, the failure pinpoints the
broken stage (analyze produced no facing anchors, or pairing/exposure mismatch).

- [ ] **Step 3: Run the whole suite**

Run: `python -m pytest -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end analyze + serve pipeline"
```

---

## Task 16: README + real-region verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Highliner Finder

Find candidate highline spots in Catalonia from ICGC LIDAR terrain.

## Setup
    python -m venv .venv && . .venv/bin/activate
    pip install -e ".[dev]"

## Use
    # 1. fetch terrain for a bbox (EPSG:25831 meters)
    highliner ingest --region montserrat --bbox 402000,4606000,406000,4610000
    #    if multiple tiles, build the mosaic:
    #    gdalbuildvrt data/montserrat/mosaic.tif data/montserrat/dtm_*.tif
    # 2. extract anchors
    highliner analyze --region montserrat
    # 3. serve the map
    highliner serve
    # open http://127.0.0.1:8000/

## Caveat
Results are candidates to scout, not confirmed-riggable lines. Terrain data
cannot reveal bolts, trees, loose rock, access, or permissions. Scout responsibly.
```

- [ ] **Step 2: Real-region verification (manual)**

Run a real ingest against a small Catalan bbox you know has cliffs (e.g.
Montserrat). Confirm `ingest` downloads a valid GeoTIFF (fix `COVERAGE_ID`/axis
labels in `ingest.py` if the WCS rejects the request — see Task 11 note), then
`analyze`, then `serve`, and eyeball whether candidate lines land on real cliff
gaps. Adjust `config.py` thresholds if results are too noisy or too sparse.

- [ ] **Step 3: Commit**

```bash
git add README.md highliner/ingest.py highliner/config.py
git commit -m "docs: add README; tune after real-region check"
```

---

## Self-Review Notes

- **Spec coverage:** ingest (T11), analyze/slope/drop-sectors/anchors (T5,6,8),
  directional sectors stored per anchor (T6,7), GeoParquet store (T7), in-memory
  KDTree pairing with directional gate + exposure + interior-low check (T9),
  three live sliders + caveat in UI (T14), API viewport query (T12), CRS in UTM
  with lon/lat only for display (T3,10,14), error handling: no region (T12),
  too-many-anchors zoom hint (T12), ICGC fetch caching (T11). DSM clearance and
  SpatiaLite scale-up correctly left out (spec "future enhancements").
- **Known real-world unknowns flagged, not hidden:** the exact ICGC WCS
  `COVERAGE_ID` and axis labels need one live check (T11/T16 notes).
- **Type consistency:** `Anchor(x,y,elev,sectors)`, `Raster(data,transform,res)`,
  `Candidate(a,b,length,exposure,height_diff)`, `find_candidates(...)`,
  `scoring.score`, `scoring.to_geojson`, `extract_anchors`, `drop_sectors`,
  `bearing_in_sectors`, `to_utm`/`to_lonlat`, `layer.clearLayers()` used
  consistently across tasks.
