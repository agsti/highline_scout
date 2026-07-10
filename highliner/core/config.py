from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

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
MAX_ANCHORS_IN_VIEW = 20000  # cap on anchors in a viewport (GET /anchors and /zones)
MAX_RESTRICTION_FEATURES = 4000  # cap protected-area polygons returned per viewport

# Zone clustering
CLUSTER_DIST_M = 50.0       # paired anchors closer than this share a zone
ZONE_BUFFER_M = 15.0        # hull buffer so 2-anchor zones render as polygons
# Serve-time dedup of near-duplicate pairs at overlapping region seams.
# Two extractions of one line can wander up to ~THIN_DIST_M apart across a
# cross-CRS seam; a (midpoint, length, bearing) signature collapses them.
SEAM_DEDUP_GRID_M = 15.0        # ~THIN_DIST_M; midpoint/length quantization
SEAM_DEDUP_BEARING_DEG = 10.0   # ~SECTOR_TOL_DEG; bearing quantization

# Chunked precompute
CHUNK_M = 10000.0           # side of each analysis chunk (meters)
MAX_PAIR_LEN = 1000.0       # longest highline searched for / stored
CHUNK_HALO_M = 1050.0       # halo so 1000 m pairs + sector radius cross the core edge
MAX_VIEW_CHUNKS = 64        # serve guard: refuse a viewport overlapping more partitions

# Loose envelope the precomputed pairs are generated at; the live sliders only
# narrow within it (defaults above are stricter and hide some real lines).
PRECOMPUTE_MIN_LEN_M = 10.0
PRECOMPUTE_MIN_EXPOSURE_M = 10.0
PRECOMPUTE_MAX_DH_M = 30.0

# Environment-driven settings. Every field can be overridden with a
# HIGHLINER_-prefixed env var (e.g. HIGHLINER_DATA_DIR=/data in Docker).
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HIGHLINER_")

    # Where ingested rasters/anchors live. Relative to the repo root, which is
    # always the working directory the app is run from.
    data_dir: Path = Path("data")


settings = Settings()
DATA_DIR = settings.data_dir

# Zoomed-out density pyramid
DENSITY_ZOOM_LEVELS = range(6, 15)  # slippy-map zoom layers precomputed (z6..z14)
DENSITY_MAX_ZOOM = 12               # frontend shows density at/below this Leaflet zoom, zones above
DENSITY_ZOOM_OFFSET = 2             # request density tiles this many levels finer than the display zoom
