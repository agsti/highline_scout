from pathlib import Path
from typing import Callable
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from highliner import cli
from highliner.repositories.anchors import load_anchors


def test_analyze_writes_anchors(tmp_path: Path) -> None:
    region = tmp_path / "demo"
    region.mkdir()
    # two-sided cliff so anchors exist
    data = np.full((61, 61), 40.0, dtype="float32")
    data[:, 28:33] = 100.0
    with rasterio.open(region / "mosaic.tif", "w", driver="GTiff", height=61,
                       width=61, count=1, dtype="float32", crs="EPSG:25831",
                       transform=from_origin(0, 122, 2.0, 2.0)) as ds:
        ds.write(data, 1)

    cli.main(["analyze", "--region", "demo", "--data-dir", str(tmp_path)])
    anchors = load_anchors(region / "anchors.parquet")
    assert len(anchors) > 0


def test_precompute_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner import cli
    calls: dict[str, object] = {}

    def fake(region: str, bbox: tuple[float, ...], data_dir: Path,
             chunk_m: float = 10000.0,
             report: Callable[[int, int], None] | None = None) -> int:
        calls["region"] = region
        calls["bbox"] = bbox
        calls["chunk_m"] = chunk_m
        if report:
            report(1, 1)
        return 1
    monkeypatch.setattr("highliner.services.precompute.precompute", fake)
    cli.main(["precompute", "--region", "catalonia", "--data-dir", "/tmp/x",
              "--bbox", "0,0,10000,10000", "--chunk-km", "10"])
    assert calls["region"] == "catalonia"
    assert calls["bbox"] == (0.0, 0.0, 10000.0, 10000.0)
    assert calls["chunk_m"] == 10000.0


def test_precompute_density_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner import cli
    calls: dict[str, object] = {}

    def fake(region_dir: Path, zoom_levels: object = None,
             report: Callable[[int, int], None] | None = None) -> int:
        calls["region_dir"] = region_dir
        if report:
            report(1, 1)
        return 7
    monkeypatch.setattr("highliner.services.density.build_density", fake)
    cli.main(["precompute-density", "--region", "catalonia", "--data-dir", "/tmp/x"])
    assert calls["region_dir"] == Path("/tmp/x") / "catalonia"
