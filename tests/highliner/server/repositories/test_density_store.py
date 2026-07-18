from pathlib import Path

import numpy as np
from highliner.core import tiles
from highliner.server.repositories import density_store
from highliner.server.repositories.density_store import DensityFilter

# Montserrat, and a viewport around it.
VIEW = (1.7, 41.5, 2.0, 41.7)
FAR_VIEW = (3.0, 42.0, 3.1, 42.1)
# Default sliders: min_len 20 -> bucket >= 2, max_len 150 -> bucket < 15,
# min_exposure 30 -> exposure bucket >= 3.
DEFAULTS = DensityFilter(min_len=20.0, max_len=150.0, min_exposure=30.0,
                         excluded_mask=0)


def _write(path: Path, hist: list[tuple[int, int, int, int]]) -> None:
    """One cell at Montserrat carrying ``hist`` rows of (hl, he, hm, hc)."""
    tx, ty = tiles.lonlat_to_tile(1.83, 41.59, 12)
    np.savez(
        path,
        cx=np.array([tx], dtype=np.int32),
        cy=np.array([ty], dtype=np.int32),
        n=np.array([sum(row[3] for row in hist)], dtype=np.int32),
        max_exp=np.array([85.0], dtype=np.float32),
        min_len=np.array([40.0], dtype=np.float32),
        max_len=np.array([120.0], dtype=np.float32),
        off=np.array([0, len(hist)], dtype=np.int64),
        hl=np.array([row[0] for row in hist], dtype=np.int16),
        he=np.array([row[1] for row in hist], dtype=np.int16),
        hm=np.array([row[2] for row in hist], dtype=np.int8),
        hc=np.array([row[3] for row in hist], dtype=np.int32),
    )


def test_select_sums_only_rows_inside_the_slider_buckets(tmp_path: Path) -> None:
    path = tmp_path / "z12.npz"
    _write(path, [(10, 3, 0, 2),    # 100 m, exposure 30 m -> kept
                  (20, 4, 0, 1),    # 200 m -> too long for max_len 150
                  (10, 1, 0, 7)])   # exposure 10 m -> below min_exposure 30

    idx, counts = density_store.read_density(path).select(12, VIEW, DEFAULTS)

    assert list(idx) == [0]
    assert list(counts) == [2]


def test_select_drops_rows_matching_any_excluded_layer(tmp_path: Path) -> None:
    path = tmp_path / "z12.npz"
    _write(path, [(10, 3, 1, 2),    # zepa
                  (10, 3, 4, 3),    # enp
                  (10, 3, 0, 5)])   # unrestricted
    zepa_and_enp = DensityFilter(min_len=20.0, max_len=150.0,
                                 min_exposure=30.0, excluded_mask=5)

    idx, counts = density_store.read_density(path).select(12, VIEW, zepa_and_enp)

    assert list(idx) == [0]
    assert list(counts) == [5]


def test_select_drops_cells_outside_the_viewport(tmp_path: Path) -> None:
    path = tmp_path / "z12.npz"
    _write(path, [(10, 3, 0, 2)])

    idx, counts = density_store.read_density(path).select(12, FAR_VIEW, DEFAULTS)

    assert len(idx) == len(counts) == 0


def test_select_drops_cells_the_filter_empties(tmp_path: Path) -> None:
    path = tmp_path / "z12.npz"
    _write(path, [(10, 1, 0, 4)])  # exposure below the 30 m default

    idx, counts = density_store.read_density(path).select(12, VIEW, DEFAULTS)

    assert len(idx) == len(counts) == 0


def test_cells_are_cached_until_the_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "z12.npz"
    _write(path, [(10, 3, 0, 2)])

    first = density_store.density_cells(path)
    assert density_store.density_cells(path) is first  # same object: cache hit

    _write(path, [(10, 3, 0, 9)])
    import os
    os.utime(path, (0, 0))  # force a distinct mtime

    second = density_store.density_cells(path)
    assert second is not first
    assert int(second.select(12, VIEW, DEFAULTS)[1][0]) == 9
