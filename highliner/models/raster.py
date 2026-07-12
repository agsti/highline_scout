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

    def values_at(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Vectorized ``value_at``: float64 elevations for arrays of UTM
        coordinates (any shape), NaN outside the raster."""
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

    def sample_line(self, x1: float, y1: float, x2: float, y2: float,
                    step: float | None = None) -> np.ndarray:
        step = step or self.res
        length = float(np.hypot(x2 - x1, y2 - y1))
        n = max(2, int(length / step) + 1)
        return self.values_at(np.linspace(x1, x2, n), np.linspace(y1, y2, n))
