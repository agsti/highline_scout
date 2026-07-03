from dataclasses import dataclass

from shapely.geometry import Polygon


@dataclass(frozen=True)
class Zone:
    polygon: Polygon            # UTM (EPSG:25831) coordinates
    height_min: float
    height_max: float
    length_min: float
    length_max: float
    n_anchors: int
    n_pairs: int
