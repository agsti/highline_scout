from dataclasses import dataclass

import numpy as np
from affine import Affine


@dataclass
class Raster:
    data: np.ndarray      # 2D float, NaN = nodata
    transform: Affine     # pixel -> UTM (EPSG:25831)
    res: float            # meters per pixel (square)

    def values_at(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Float64 elevations for arrays of UTM coordinates (any shape), NaN
        outside the raster. Cell lookup floors, so a coordinate on a shared
        edge belongs to the higher-indexed cell."""
        inv = ~self.transform
        xs = np.asarray(xs, dtype="float64")
        ys = np.asarray(ys, dtype="float64")
        cols = np.floor(inv.a * xs + inv.b * ys + inv.c).astype(np.int64)
        rows = np.floor(inv.d * xs + inv.e * ys + inv.f).astype(np.int64)
        h, w = self.data.shape
        inside = (rows >= 0) & (rows < h) & (cols >= 0) & (cols < w)
        out = np.full(xs.shape, np.nan)
        out[inside] = self.data[rows[inside], cols[inside]].astype("float64")
        return out
