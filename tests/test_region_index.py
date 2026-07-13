import json
from pathlib import Path
from typing import Any

from highliner.server.router import deps

from tests.helpers import to_utm


def _write_grid(data_dir: Path, name: str,
                bbox: tuple[float, float, float, float],
                crs: str | None = None, country: str = "spain") -> None:
    rdir = data_dir / country / name
    rdir.mkdir(parents=True)
    grid: dict[str, Any] = {"bbox": list(bbox), "chunk_m": 10000.0}
    if crs is not None:
        grid["crs"] = crs
    (rdir / "grid.json").write_text(json.dumps(grid))


def test_build_index_skips_dirs_without_grid(tmp_path: Path) -> None:
    cx, cy = to_utm(1.83, 41.59)
    _write_grid(tmp_path, "cat", (cx - 500, cy - 500, cx + 500, cy + 500))
    (tmp_path / "not_a_region").mkdir()  # no grid.json

    index = deps.build_region_index(tmp_path)
    assert [e.name for e in index] == ["cat"]
    w, s, e, n = index[0].lonlat_bounds
    assert w < e and s < n
    assert w <= 1.83 <= e and s <= 41.59 <= n


def test_regions_in_view_filters_by_overlap(tmp_path: Path) -> None:
    cx, cy = to_utm(1.83, 41.59)       # Catalonia
    gx, gy = to_utm(-8.0, 42.8)        # Galicia (far west)
    _write_grid(tmp_path, "cat", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_grid(tmp_path, "gal", (gx - 500, gy - 500, gx + 500, gy + 500))

    index = deps.build_region_index(tmp_path)
    hits = deps.regions_in_view(index, (1.82, 41.58, 1.84, 41.60))
    assert [e.name for e in hits] == ["cat"]


def test_build_index_sets_country_from_partition(tmp_path: Path) -> None:
    cx, cy = to_utm(1.83, 41.59)
    _write_grid(tmp_path, "cat", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_grid(tmp_path, "alps", (cx - 500, cy - 500, cx + 500, cy + 500),
                country="france")

    index = deps.build_region_index(tmp_path)
    assert {(e.name, e.country) for e in index} == {("cat", "spain"),
                                                    ("alps", "france")}
    assert [e.name for e in deps.regions_in_country(index, "france")] == ["alps"]


def test_build_index_empty_when_data_dir_missing(tmp_path: Path) -> None:
    assert deps.build_region_index(tmp_path / "nope") == []


def test_get_region_index_is_cached(tmp_path: Path) -> None:
    from types import SimpleNamespace

    cx, cy = to_utm(1.83, 41.59)
    _write_grid(tmp_path, "cat", (cx - 500, cy - 500, cx + 500, cy + 500))

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(data_dir=tmp_path)))
    first = deps.get_region_index(request)  # type: ignore[arg-type]
    second = deps.get_region_index(request)  # type: ignore[arg-type]
    assert first is second  # built once, then served from app.state cache
