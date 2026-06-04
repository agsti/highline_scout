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

# Web-triggered analysis jobs
MAX_ANALYZE_TILES = 200     # reject POST /analyze whose bbox needs more tiles
HUEY_DB = DATA_DIR / "huey.db"
