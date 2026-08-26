"""Tests for the coastal-chunk finder/deleter rollout script."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import box

_SPEC = importlib.util.spec_from_file_location(
    "find_coastal_chunks",
    Path(__file__).parents[2] / "scripts" / "find_coastal_chunks.py")
assert _SPEC is not None and _SPEC.loader is not None
find_coastal_chunks = importlib.util.module_from_spec(_SPEC)
# dataclasses looks its defining module up in sys.modules by __module__;
# without this, @dataclass on a spec-loaded module raises AttributeError.
sys.modules[_SPEC.name] = find_coastal_chunks
_SPEC.loader.exec_module(find_coastal_chunks)


def test_coastal_chunk_ids_selects_only_chunks_whose_halo_intersects_ocean() -> None:
    # 2x1 grid of 10_000 m chunks: chunk (0,0) spans x[0,10000], chunk (1,0)
    # spans x[10000,20000]. Ocean sits at x>=15000, well clear of chunk (0,0)
    # even with a 1050 m halo (halo edge lands at x=11050 < 15000).
    bbox = (0.0, 0.0, 20000.0, 10000.0)
    ocean_geom = box(15000.0, -5000.0, 30000.0, 15000.0)

    ids = find_coastal_chunks.coastal_chunk_ids(
        bbox, chunk_m=10000.0, ocean_geom=ocean_geom, halo=1050.0)

    assert ids == [(1, 0)]


def _write_region(region_dir: Path, bbox: tuple[float, float, float, float],
                  chunk_m: float = 10000.0, crs: str = "EPSG:32719") -> None:
    region_dir.mkdir(parents=True)
    (region_dir / "grid.json").write_text(json.dumps({
        "bbox": list(bbox), "chunk_m": chunk_m, "crs": crs,
        "dtm_source": "test"}))


def test_plan_region_lists_coastal_chunk_files_and_the_region_density_dir(
        tmp_path: Path) -> None:
    region_dir = tmp_path / "demo"
    _write_region(region_dir, (0.0, 0.0, 20000.0, 10000.0))
    (region_dir / "anchors").mkdir()
    (region_dir / "pairs").mkdir()
    (region_dir / "density").mkdir()
    for cx, cy in [(0, 0), (1, 0)]:
        (region_dir / "anchors" / f"p_{cx}_{cy}.parquet").write_bytes(b"")
        (region_dir / "pairs" / f"q_{cx}_{cy}.parquet").write_bytes(b"")
    (region_dir / "density" / "z10.npz").write_bytes(b"")
    ocean_geom = box(15000.0, -5000.0, 30000.0, 15000.0)   # only chunk (1,0)

    plan = find_coastal_chunks.plan_region(region_dir, ocean_geom, halo=1050.0)

    assert plan.total_chunks == 2
    assert plan.coastal_chunk_ids == [(1, 0)]
    assert sorted(p.name for p in plan.chunk_files) == [
        "p_1_0.parquet", "q_1_0.parquet"]
    assert plan.density_dir == region_dir / "density"


def test_plan_region_skips_missing_chunk_files(tmp_path: Path) -> None:
    # Chunk (1,0) is coastal but was never actually computed (no anchors/
    # pairs on disk) -- plan_region must not report files that don't exist.
    region_dir = tmp_path / "demo"
    _write_region(region_dir, (0.0, 0.0, 20000.0, 10000.0))
    ocean_geom = box(15000.0, -5000.0, 30000.0, 15000.0)

    plan = find_coastal_chunks.plan_region(region_dir, ocean_geom, halo=1050.0)

    assert plan.coastal_chunk_ids == [(1, 0)]
    assert plan.chunk_files == []


def test_plan_region_no_coastal_chunks_means_no_density_deletion(
        tmp_path: Path) -> None:
    region_dir = tmp_path / "demo"
    _write_region(region_dir, (0.0, 0.0, 20000.0, 10000.0))
    (region_dir / "density").mkdir()
    (region_dir / "density" / "z10.npz").write_bytes(b"")
    ocean_geom = box(100000.0, 100000.0, 200000.0, 200000.0)  # nowhere near

    plan = find_coastal_chunks.plan_region(region_dir, ocean_geom, halo=1050.0)

    assert plan.coastal_chunk_ids == []
    assert plan.chunk_files == []
    assert plan.density_dir is None


def _setup_country(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One country, one coastal region (chunk (1,0)) with computed data."""
    data_dir = tmp_path / "data"
    region_dir = data_dir / "chile" / "coastal_region"
    _write_region(region_dir, (0.0, 0.0, 20000.0, 10000.0))
    (region_dir / "anchors").mkdir()
    (region_dir / "pairs").mkdir()
    (region_dir / "density").mkdir()
    for cx, cy in [(0, 0), (1, 0)]:
        (region_dir / "anchors" / f"p_{cx}_{cy}.parquet").write_bytes(b"")
        (region_dir / "pairs" / f"q_{cx}_{cy}.parquet").write_bytes(b"")
    (region_dir / "density" / "z10.npz").write_bytes(b"")

    ocean_geom = box(15000.0, -5000.0, 30000.0, 15000.0)   # only chunk (1,0)
    monkeypatch.setattr(find_coastal_chunks.ocean, "load_ocean_geometry",
                        lambda crs: ocean_geom)
    return data_dir


def test_main_dry_run_leaves_files_in_place(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = _setup_country(tmp_path, monkeypatch)
    region_dir = data_dir / "chile" / "coastal_region"

    code = find_coastal_chunks.main(["chile", "--data-dir", str(data_dir)])

    assert code == 0
    assert (region_dir / "anchors" / "p_1_0.parquet").exists()
    assert (region_dir / "pairs" / "q_1_0.parquet").exists()
    assert (region_dir / "density" / "z10.npz").exists()
    out = capsys.readouterr().out
    assert "would delete" in out
    assert "--delete" in out
    assert "just etl-chunk chile" in out
    assert "just etl-density chile" in out


def test_main_delete_removes_coastal_chunk_and_density_files(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = _setup_country(tmp_path, monkeypatch)
    region_dir = data_dir / "chile" / "coastal_region"

    code = find_coastal_chunks.main(
        ["chile", "--data-dir", str(data_dir), "--delete"])

    assert code == 0
    assert not (region_dir / "anchors" / "p_1_0.parquet").exists()
    assert not (region_dir / "pairs" / "q_1_0.parquet").exists()
    assert not (region_dir / "density" / "z10.npz").exists()
    # the non-coastal chunk's files are untouched
    assert (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert (region_dir / "pairs" / "q_0_0.parquet").exists()
    out = capsys.readouterr().out
    assert "deleted" in out
    assert "just etl-chunk chile" in out
    assert "just etl-density chile" in out


def test_main_reports_nothing_to_do_when_no_chunks_are_coastal(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "data"
    region_dir = data_dir / "chile" / "inland_region"
    _write_region(region_dir, (0.0, 0.0, 20000.0, 10000.0))
    ocean_geom = box(100000.0, 100000.0, 200000.0, 200000.0)  # nowhere near
    monkeypatch.setattr(find_coastal_chunks.ocean, "load_ocean_geometry",
                        lambda crs: ocean_geom)

    code = find_coastal_chunks.main(["chile", "--data-dir", str(data_dir)])

    assert code == 0
    out = capsys.readouterr().out
    assert "nothing to do" in out
    assert "just etl-chunk" not in out


def test_main_returns_nonzero_when_country_has_no_regions(
        tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    code = find_coastal_chunks.main(["nowhere", "--data-dir", str(data_dir)])

    assert code == 1
