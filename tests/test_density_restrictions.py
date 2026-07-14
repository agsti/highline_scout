from pathlib import Path

import geopandas as gpd
from highliner.etl.density.restrictions import (
    anchor_mask,
    candidate_mask,
    load_layers,
)
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from shapely.geometry import box


def _candidate(ax: float, ay: float, bx: float, by: float) -> Candidate:
    a = Anchor(x=ax, y=ay, elev=100.0, sectors=())
    b = Anchor(x=bx, y=by, elev=100.0, sectors=())
    return Candidate(a=a, b=b, length=30.0, exposure=30.0, height_diff=0.0)


def _write_layer(path: Path, geometry: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame({"name": ["test"] * len(geometry)}, geometry=geometry,
                     crs="EPSG:25831").to_parquet(path)


def test_either_anchor_sets_the_layer_bit(tmp_path: Path) -> None:
    _write_layer(tmp_path / "zepa.parquet", [box(0, 0, 10, 10)])
    layers = load_layers(tmp_path, "EPSG:25831")
    assert candidate_mask(_candidate(5, 5, 30, 30), layers) == 1


def test_boundary_and_multilayer_overlap_are_included(tmp_path: Path) -> None:
    _write_layer(tmp_path / "zepa.parquet", [box(0, 0, 10, 10)])
    _write_layer(tmp_path / "enp.parquet", [box(0, 0, 10, 10)])
    layers = load_layers(tmp_path, "EPSG:25831")
    assert candidate_mask(_candidate(10, 5, 30, 30), layers) == 5


def test_missing_layer_files_produce_no_mask(tmp_path: Path) -> None:
    layers = load_layers(tmp_path, "EPSG:25831")
    assert candidate_mask(_candidate(1, 1, 2, 2), layers) == 0


def test_anchor_mask_is_reused_from_the_worker_cache(tmp_path: Path) -> None:
    _write_layer(tmp_path / "zepa.parquet", [box(0, 0, 10, 10)])
    layers = load_layers(tmp_path, "EPSG:25831")
    anchor = Anchor(x=5, y=5, elev=100.0, sectors=())
    cache: dict[tuple[float, float], int] = {}

    assert anchor_mask(anchor, layers, cache) == 1
    layers["zepa"] = layers["zepa"].iloc[0:0]

    assert anchor_mask(anchor, layers, cache) == 1
