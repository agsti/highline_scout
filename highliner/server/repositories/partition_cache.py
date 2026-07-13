"""Columnar, process-cached reads of the chunked parquet partitions.

Each partition is read once, parsed into NumPy columns, and cached keyed on
``(path, mtime)``. Viewport and slider filtering then run as vectorized masks
over the cached columns, and only the surviving rows are turned into domain
objects. On a warm cache this keeps the serve hot path off both disk and the
per-row Python object boundary — panning re-requests the same partition files,
so the hit rate stays high even though no two viewports are identical.

The write side and stored-column layout live in
``highliner.etl.chunk.{candidates,anchors}``.
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

import numpy as np
from numpy.typing import NDArray

from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate, PairFilter

Bbox = tuple[float, float, float, float]
FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True)
class PairColumns:
    """One NumPy column per stored pair field (see ``save_candidates``)."""
    ax: FloatArray
    ay: FloatArray
    aelev: FloatArray
    bx: FloatArray
    by: FloatArray
    belev: FloatArray
    length: FloatArray
    exposure: FloatArray
    height_diff: FloatArray

    def select(self, bbox: Bbox, pair_filter: PairFilter | None) -> list[Candidate]:
        """Candidates whose segment intersects ``bbox`` and (if given) pass the
        slider thresholds. Only the survivors are materialized."""
        mask = self._bbox_mask(bbox)
        if pair_filter is not None:
            mask &= self._filter_mask(pair_filter)
        return self._materialize(mask)

    def to_candidates(self) -> list[Candidate]:
        """Every stored pair as a ``Candidate`` (used by the offline density
        aggregation, which streams each partition once)."""
        return self._materialize(None)

    def _bbox_mask(self, bbox: Bbox) -> BoolArray:
        minx, miny, maxx, maxy = bbox
        lox = np.minimum(self.ax, self.bx)
        hix = np.maximum(self.ax, self.bx)
        loy = np.minimum(self.ay, self.by)
        hiy = np.maximum(self.ay, self.by)
        return (lox <= maxx) & (hix >= minx) & (loy <= maxy) & (hiy >= miny)

    def _filter_mask(self, pf: PairFilter) -> BoolArray:
        return ((self.length >= pf.min_len) & (self.length <= pf.max_len)
                & (self.exposure >= pf.min_exposure)
                & (self.height_diff <= pf.max_dh))

    def _materialize(self, mask: BoolArray | None) -> list[Candidate]:
        idx = range(len(self.length)) if mask is None else np.nonzero(mask)[0]
        out: list[Candidate] = []
        for i in idx:
            a = Anchor(x=float(self.ax[i]), y=float(self.ay[i]),
                       elev=float(self.aelev[i]), sectors=())
            b = Anchor(x=float(self.bx[i]), y=float(self.by[i]),
                       elev=float(self.belev[i]), sectors=())
            out.append(Candidate(a=a, b=b, length=float(self.length[i]),
                                 exposure=float(self.exposure[i]),
                                 height_diff=float(self.height_diff[i])))
        return out


@dataclass(frozen=True)
class AnchorColumns:
    x: FloatArray
    y: FloatArray
    elev: FloatArray
    sectors: tuple[str, ...]  # raw JSON strings; parsed only for survivors

    def select(self, bbox: Bbox) -> list[Anchor]:
        """Anchors inside ``bbox``. Only the survivors are materialized (and
        only their sector JSON is parsed)."""
        minx, miny, maxx, maxy = bbox
        mask = ((self.x >= minx) & (self.x <= maxx)
                & (self.y >= miny) & (self.y <= maxy))
        out: list[Anchor] = []
        for i in np.nonzero(mask)[0]:
            secs: tuple[tuple[float, float, float], ...] = tuple(
                tuple(s) for s in json.loads(self.sectors[i]))
            out.append(Anchor(x=float(self.x[i]), y=float(self.y[i]),
                              elev=float(self.elev[i]), sectors=secs))
        return out


def read_pair_columns(path: str | Path) -> PairColumns:
    """Read a pairs partition into columns (uncached)."""
    import pandas as pd
    df = pd.read_parquet(path)

    def col(name: str) -> FloatArray:
        return cast(FloatArray, df[name].to_numpy(dtype=np.float64))

    return PairColumns(
        ax=col("ax"), ay=col("ay"), aelev=col("aelev"),
        bx=col("bx"), by=col("by"), belev=col("belev"),
        length=col("length"), exposure=col("exposure"),
        height_diff=col("height_diff"))


def read_anchor_columns(path: str | Path) -> AnchorColumns:
    """Read an anchors partition into columns (uncached)."""
    import geopandas as gpd
    gdf = gpd.read_parquet(path)
    geom = gdf.geometry
    return AnchorColumns(
        x=geom.x.to_numpy(dtype=np.float64),
        y=geom.y.to_numpy(dtype=np.float64),
        elev=gdf["elev"].to_numpy(dtype=np.float64),
        sectors=tuple(str(s) for s in gdf["sectors"].tolist()))


@lru_cache(maxsize=config.PARTITION_CACHE_MAXSIZE)
def _pair_columns(path_str: str, mtime_ns: int) -> PairColumns:
    del mtime_ns  # part of the cache key only; a changed mtime re-reads the file
    return read_pair_columns(path_str)


@lru_cache(maxsize=config.PARTITION_CACHE_MAXSIZE)
def _anchor_columns(path_str: str, mtime_ns: int) -> AnchorColumns:
    del mtime_ns  # part of the cache key only; a changed mtime re-reads the file
    return read_anchor_columns(path_str)


def pair_columns(path: str | Path) -> PairColumns:
    """Cached pairs columns; re-read only when the file's mtime changes."""
    p = Path(path)
    return _pair_columns(str(p), p.stat().st_mtime_ns)


def anchor_columns(path: str | Path) -> AnchorColumns:
    """Cached anchor columns; re-read only when the file's mtime changes."""
    p = Path(path)
    return _anchor_columns(str(p), p.stat().st_mtime_ns)
