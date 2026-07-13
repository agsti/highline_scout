from collections.abc import Callable
from pathlib import Path

import pytest
from highliner import cli


def test_precompute_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake(region: str, bbox: tuple[float, ...], data_dir: Path,  # noqa: PLR0913
             chunk_m: float = 10000.0,
             report: Callable[[int, int], None] | None = None,
             crs: str | None = None,
             dtm_source: str | None = None,
             workers: int = 1) -> int:
        calls["region"] = region
        calls["bbox"] = bbox
        calls["chunk_m"] = chunk_m
        calls["crs"] = crs
        calls["dtm_source"] = dtm_source
        calls["workers"] = workers
        if report:
            report(1, 1)
        return 1
    monkeypatch.setattr("highliner.etl.services.precompute.precompute", fake)
    cli.main(["precompute", "--region", "catalonia", "--data-dir", "/tmp/x",
              "--bbox", "0,0,10000,10000", "--chunk-km", "10",
              "--workers", "4"])
    assert calls["region"] == "catalonia"
    assert calls["bbox"] == (0.0, 0.0, 10000.0, 10000.0)
    assert calls["chunk_m"] == 10000.0
    assert calls["crs"] == "EPSG:25831"
    assert calls["dtm_source"] == "icgc"
    assert calls["workers"] == 4


def test_precompute_density_command(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake(region_dir: Path, zoom_levels: object = None,
             report: Callable[[int, int], None] | None = None) -> int:
        calls["region_dir"] = region_dir
        if report:
            report(1, 1)
        return 7
    monkeypatch.setattr("highliner.etl.services.density.build_density", fake)
    cli.main(["precompute-density", "--region", "catalonia", "--data-dir", "/tmp/x"])
    assert calls["region_dir"] == Path("/tmp/x") / "spain" / "catalonia"
