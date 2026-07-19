import json
import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import box

from highliner.core import config, tiles
from highliner.etls.chunk.candidates import save_candidates
from highliner.etls.density import builder
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from tests.helpers import to_utm


def _pair(mx: float, my: float, exposure: float, spread: float = 40.0) -> Candidate:
    """A candidate whose two anchors straddle midpoint ``(mx, my)`` by ``spread`` m,
    so the representative point sits away from either endpoint."""
    a = Anchor(x=mx - spread, y=my, elev=100.0, sectors=())
    b = Anchor(x=mx + spread, y=my, elev=100.0, sectors=())
    return Candidate(a=a, b=b, length=2 * spread, exposure=exposure, height_diff=0.0)


def _write_region(tmp_path: Path, pairs: list[Candidate]) -> Path:
    region = tmp_path / "catalonia"
    (region / "pairs").mkdir(parents=True)
    (region / "grid.json").write_text(json.dumps({
        "bbox": [0, 0, 1, 1], "chunk_m": 1, "crs": "EPSG:25831",
    }))
    save_candidates(pairs, region / "pairs" / "q_0_0.parquet")
    return region


def _load(region: Path, zoom: int) -> dict[str, np.ndarray]:
    """The arrays of one written density zoom layer."""
    with np.load(region / "density" / f"z{zoom}.npz") as data:
        return {key: data[key] for key in data.files}


def test_two_pairs_share_a_cell_third_apart(tmp_path: Path) -> None:
    # Two pairs at the same midpoint (Montserrat area, UTM), one ~5 km away.
    near = to_utm(1.83, 41.59)
    far = to_utm(1.90, 41.59)
    p1 = _pair(near[0], near[1], exposure=40.0, spread=40.0)   # length 80
    p2 = _pair(near[0], near[1], exposure=70.0, spread=25.0)   # length 50
    p3 = _pair(far[0], far[1], exposure=25.0)
    region = _write_region(tmp_path, [p1, p2, p3])

    total = builder.build_density(region, zoom_levels=[12])

    cells = _load(region, 12)
    assert total == len(cells["cx"]) == 2
    shared = tiles.lonlat_to_tile(1.83, 41.59, 12)
    i = int(np.nonzero(
        (cells["cx"] == shared[0]) & (cells["cy"] == shared[1]))[0][0])
    assert cells["n"][i] == 2
    assert cells["max_exp"][i] == 70.0  # max across the shared cell's pairs
    assert cells["min_len"][i] == 50.0  # min/max length across the cell's pairs
    assert cells["max_len"][i] == 80.0


def test_report_and_default_zooms(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=50.0)])
    seen: list[tuple[int, int]] = []

    builder.build_density(region, report=lambda d, t: seen.append((d, t)))

    for z in config.DENSITY_ZOOM_LEVELS:
        assert (region / "density" / f"z{z}.npz").exists()
    assert seen and seen[-1][0] == seen[-1][1]  # progress reaches 100%


def test_cell_writes_sparse_length_exposure_mask_histogram(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    pairs = [
        _pair(near[0], near[1], exposure=30.0, spread=50.0),
        _pair(near[0], near[1], exposure=39.0, spread=52.5),
        _pair(near[0], near[1], exposure=40.0, spread=100.0),
    ]
    region = _write_region(tmp_path, pairs)

    builder.build_density(region, zoom_levels=[12],
                          restrictions_dir=tmp_path / "spain" / "restrictions")

    cells = _load(region, 12)
    assert list(cells["off"]) == [0, 2]  # one cell, two histogram rows
    rows = list(zip(cells["hl"], cells["he"], cells["hm"], cells["hc"],
                    strict=True))
    assert rows == [(10, 3, 0, 2), (20, 4, 0, 1)]


def test_builder_uses_country_restrictions(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=30.0)])
    path = tmp_path / "france" / "restrictions" / "zepa.parquet"
    path.parent.mkdir(parents=True)
    gpd.GeoDataFrame({"name": ["test"]}, geometry=[box(
        near[0] - 50, near[1] - 50, near[0], near[1] + 50)],
        crs="EPSG:25831").to_parquet(path)

    builder.build_density(region, zoom_levels=[12],
                          restrictions_dir=path.parent)

    assert _load(region, 12)["hm"][0] == 1


def test_builder_defaults_to_its_region_country_restrictions(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path / "italy", [
        _pair(near[0], near[1], exposure=30.0),
    ])
    italy_path = tmp_path / "italy" / "restrictions" / "zps.parquet"
    italy_path.parent.mkdir(parents=True)
    gpd.GeoDataFrame({"name": ["test"]}, geometry=[box(
        near[0] - 50, near[1] - 50, near[0], near[1] + 50)],
        crs="EPSG:25831").to_parquet(italy_path)
    spain_dir = tmp_path / "spain" / "restrictions"
    spain_dir.mkdir(parents=True)
    spain_restriction = gpd.GeoDataFrame({"name": ["test"]}, geometry=[box(
        near[0] - 50, near[1] - 50, near[0], near[1] + 50)],
        crs="EPSG:25831")
    for layer_id in ("zepa", "zec", "enp"):
        spain_restriction.to_parquet(spain_dir / f"{layer_id}.parquet")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)

    builder.build_density(region, zoom_levels=[12])

    assert _load(region, 12)["hm"][0] == 8


def test_parallel_density_matches_single_worker_output(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = tmp_path / "catalonia"
    pairs_dir = region / "pairs"
    pairs_dir.mkdir(parents=True)
    (region / "grid.json").write_text(json.dumps({
        "bbox": [0, 0, 1, 1], "chunk_m": 1, "crs": "EPSG:25831",
    }))
    save_candidates([_pair(near[0], near[1], exposure=30.0)],
                    pairs_dir / "q_0_0.parquet")
    save_candidates([_pair(near[0] + 20, near[1], exposure=40.0)],
                    pairs_dir / "q_1_0.parquet")

    builder.build_density(region, zoom_levels=[12], workers=1,
                          restrictions_dir=tmp_path / "spain" / "restrictions")
    serial = _load(region, 12)
    shutil.rmtree(region / "density")
    builder.build_density(region, zoom_levels=[12], workers=2,
                          restrictions_dir=tmp_path / "spain" / "restrictions")

    parallel = _load(region, 12)
    assert serial.keys() == parallel.keys()
    for key in serial:
        np.testing.assert_array_equal(serial[key], parallel[key])


def test_density_rejects_invalid_worker_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workers"):
        builder.build_density(tmp_path, workers=0)


def test_existing_nonempty_zoom_is_skipped(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=30.0)])
    density_file = region / "density" / "z12.npz"
    density_file.parent.mkdir()
    density_file.write_bytes(b"already built")

    written = builder.build_density(region, zoom_levels=[12])

    assert written == 0
    assert density_file.read_bytes() == b"already built"


def test_existing_empty_zoom_is_rebuilt(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=30.0)])
    density_file = region / "density" / "z12.npz"
    density_file.parent.mkdir()
    density_file.touch()

    written = builder.build_density(region, zoom_levels=[12])

    assert written == 1
    assert density_file.stat().st_size > 0


def test_density_rolls_finest_histograms_up_to_requested_zooms(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=30.0)])
    calls: list[int] = []
    original = tiles.lonlat_to_tile

    def record_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
        calls.append(zoom)
        return original(lon, lat, zoom)

    monkeypatch.setattr(tiles, "lonlat_to_tile", record_tile)
    builder.build_density(region, zoom_levels=[12, 13, 14])

    assert calls == [14]
    for zoom in (12, 13, 14):
        assert _load(region, zoom)["n"][0] == 1
