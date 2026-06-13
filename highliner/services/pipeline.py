from pathlib import Path
from highliner.core import config
from highliner.repositories import dtm
from highliner.models.raster import Raster
from highliner.services.terrain import extract_anchors
from highliner.repositories.anchors import save_anchors


def analyze_area(bbox, region: str, data_dir, report=None) -> int:
    """Fetch DTM for bbox, extract anchors, save them. Returns anchor count.

    report(phase, done, total) is called for progress; phase is
    'downloading' then 'extracting'.
    """
    data_dir = Path(data_dir)

    def _noop(phase, done, total):
        pass
    report = report or _noop

    total = dtm.estimate_tiles(bbox)
    report("downloading", 0, total)
    mosaic = dtm.fetch_dtm(
        bbox, region, data_dir,
        progress=lambda d, t: report("downloading", d, t))

    report("extracting", 0, 0)
    raster = Raster.open(mosaic)
    anchors = extract_anchors(
        raster, slope_min=config.SLOPE_MIN_DEG, radius=config.DROP_RADIUS_M,
        n_azimuths=config.N_AZIMUTHS, min_sector_drop=config.MIN_SECTOR_DROP_M,
        thin_dist=config.THIN_DIST_M)
    save_anchors(anchors, data_dir / region / "anchors.parquet")
    return len(anchors)
