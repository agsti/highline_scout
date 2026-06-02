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
