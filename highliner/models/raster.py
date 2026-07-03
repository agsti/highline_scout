from dataclasses import dataclass
from pathlib import Path
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

    def sample_line(self, x1: float, y1: float, x2: float, y2: float,
                    step: float | None = None) -> np.ndarray:
        step = step or self.res
        length = float(np.hypot(x2 - x1, y2 - y1))
        n = max(2, int(length / step) + 1)
        xs = np.linspace(x1, x2, n)
        ys = np.linspace(y1, y2, n)
        return np.array([self.value_at(float(x), float(y)) for x, y in zip(xs, ys)])

    # ICGC encodes the sea surface with this sentinel, distinct from the ArcGrid
    # NODATA (-9999) for out-of-coverage. Unmasked it reads as a real -8888 m
    # elevation, turning every coastal cell into a spurious ~8888 m cliff.
    SEA_SENTINEL = -8888.0

    @classmethod
    def open(cls, path: str | Path) -> "Raster":
        import rasterio
        with rasterio.open(path) as ds:
            arr = ds.read(1).astype("float32")
            if ds.nodata is not None:
                arr[arr == ds.nodata] = np.nan
            arr[arr == cls.SEA_SENTINEL] = np.nan
            return cls(data=arr, transform=ds.transform, res=abs(ds.transform.a))
