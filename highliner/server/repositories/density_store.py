"""Columnar, process-cached reads of the density pyramid.

Each ``density/z{z}.npz`` is read once into NumPy arrays and cached keyed on
``(path, mtime)``; the viewport clip and the slider/restriction filters then run
as vectorized masks. Re-parsing the layer per request is what made ``/density``
slow, so the hot path must stay off both disk and the per-cell Python loop.

Cells and histogram rows are stored CSR-style: cell ``i``'s histogram rows are
``hl/he/hm/hc[off[i]:off[i + 1]]``. The write side lives in
``highliner.etls.density.builder``.
"""
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from highliner.core import config, tiles
from highliner.core.density import BUCKET_M

IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]
FloatArray = NDArray[np.float64]
LonLatBox = tuple[float, float, float, float]

_ARRAY_NAMES = ("cx", "cy", "n", "max_exp", "min_len", "max_len",
                "off", "hl", "he", "hm", "hc")


@dataclass(frozen=True)
class DensityFilter:
    min_len: float
    max_len: float
    min_exposure: float
    excluded_mask: int


@dataclass(frozen=True)
class DensityCells:
    """One zoom layer's arrays (see ``_ARRAY_NAMES``)."""
    cx: NDArray[np.int32]
    cy: NDArray[np.int32]
    n: NDArray[np.int32]
    max_exp: NDArray[np.float32]
    min_len: NDArray[np.float32]
    max_len: NDArray[np.float32]
    off: NDArray[np.int64]
    hl: NDArray[np.int16]
    he: NDArray[np.int16]
    hm: NDArray[np.int8]
    hc: NDArray[np.int32]

    def select(self, zoom: int, view: LonLatBox,
               density_filter: DensityFilter) -> tuple[IntArray, IntArray]:
        """Return visible cells with non-zero filtered counts and their counts."""
        west, south, east, north = tiles.tile_bounds_lonlat_arrays(
            zoom, self.cx, self.cy)
        vw, vs, ve, vn = view
        visible = ((west <= ve) & (east >= vw)
                   & (south <= vn) & (north >= vs))
        totals = self._filtered_totals(self._filtered_rows(density_filter))
        idx = np.nonzero(visible & (totals > 0))[0]
        return idx, totals[idx]

    def select_with_bounds(
            self, zoom: int, view: LonLatBox, density_filter: DensityFilter,
    ) -> tuple[IntArray, IntArray, FloatArray, FloatArray]:
        """Return visible filtered cells with histogram-derived tooltip bounds."""
        west, south, east, north = tiles.tile_bounds_lonlat_arrays(
            zoom, self.cx, self.cy)
        vw, vs, ve, vn = view
        visible = ((west <= ve) & (east >= vw)
                   & (south <= vn) & (north >= vs))
        keep = self._filtered_rows(density_filter)
        totals = self._filtered_totals(keep)
        idx = np.nonzero(visible & (totals > 0))[0]
        row_cells = np.repeat(np.arange(len(self.cx)), np.diff(self.off))
        lower = np.full(len(self.cx), np.iinfo(np.int16).max, dtype=np.int16)
        upper = np.full(len(self.cx), np.iinfo(np.int16).min, dtype=np.int16)
        np.minimum.at(lower, row_cells[keep], self.hl[keep])
        np.maximum.at(upper, row_cells[keep], self.hl[keep])
        minimum = np.maximum(lower[idx] * BUCKET_M, density_filter.min_len)
        maximum = np.minimum((upper[idx] + 1) * BUCKET_M, density_filter.max_len)
        return idx, totals[idx], minimum.astype(float), maximum.astype(float)

    def _filtered_rows(self, density_filter: DensityFilter) -> BoolArray:
        """Return histogram rows that satisfy sliders and exclusion filters."""
        keep = ((self.hl >= math.ceil(density_filter.min_len / BUCKET_M))
                & (self.hl < math.ceil(density_filter.max_len / BUCKET_M))
                & (self.he >= math.ceil(density_filter.min_exposure / BUCKET_M)))
        if density_filter.excluded_mask:
            keep &= (self.hm & density_filter.excluded_mask) == 0
        return keep

    def _filtered_totals(self, keep: BoolArray) -> IntArray:
        """Sum already-filtered histogram rows for every cell."""
        cumulative = np.concatenate((
            np.zeros(1, dtype=np.int64),
            np.cumsum(np.where(keep, self.hc, 0), dtype=np.int64)))
        return cumulative[self.off[1:]] - cumulative[self.off[:-1]]


def read_density(path: str | Path) -> DensityCells:
    """Read one zoom layer into arrays without using the process cache."""
    with np.load(path) as data:
        return DensityCells(**{name: data[name] for name in _ARRAY_NAMES})


@lru_cache(maxsize=config.DENSITY_CACHE_MAXSIZE)
def _density_cells(path_str: str, mtime_ns: int) -> DensityCells:
    del mtime_ns  # Part of the cache key only; a changed mtime re-reads the file.
    return read_density(path_str)


def density_cells(path: str | Path) -> DensityCells:
    """Return cached cells, re-reading only after the path's mtime changes."""
    density_path = Path(path)
    return _density_cells(str(density_path), density_path.stat().st_mtime_ns)
