from pathlib import Path

import pytest
from highliner.etl.chunk import main as chunk_main
from highliner.etl.density import main as density_main
from highliner.restrictions import main as restrictions_main
from highliner.server import main as server_main


def test_server_command_starts_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_create_app(data_dir: Path) -> object:
        calls["data_dir"] = data_dir
        return object()

    def fake_run(app: object, host: str, port: int) -> None:
        calls.update(app=app, host=host, port=port)

    monkeypatch.setattr("highliner.server.main.create_app", fake_create_app)
    monkeypatch.setattr("highliner.server.main.uvicorn.run", fake_run)
    server_main.main(["--data-dir", "/tmp/x", "--host", "0.0.0.0",
                      "--port", "9000"])
    assert calls["data_dir"] == Path("/tmp/x")
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 9000


def test_chunk_command_uses_region_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake(region: str, bbox: tuple[float, ...], data_dir: Path,
             **kwargs: object) -> int:
        calls.update(region=region, bbox=bbox, data_dir=data_dir, **kwargs)
        return 1

    monkeypatch.setattr("highliner.etl.chunk.precompute.precompute", fake)
    chunk_main.main(["--region", "catalonia", "--data-dir", "/tmp/x",
                     "--bbox", "0,0,10000,10000", "--chunk-km", "10",
                     "--workers", "4"])
    assert calls["region"] == "catalonia"
    assert calls["bbox"] == (0.0, 0.0, 10000.0, 10000.0)
    assert calls["chunk_m"] == 10000.0
    assert calls["crs"] == "EPSG:25831"
    assert calls["dtm_source"] == "icgc"
    assert calls["workers"] == 4


def test_density_command_uses_region_directory(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake(region_dir: Path, **kwargs: object) -> int:
        calls["region_dir"] = region_dir
        return 7

    monkeypatch.setattr("highliner.etl.services.density.build_density", fake)
    density_main.main(["--region", "catalonia", "--data-dir", "/tmp/x"])
    assert calls["region_dir"] == Path("/tmp/x") / "spain" / "catalonia"


def test_restrictions_command_builds_layers(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(restrictions_main, "fetch_all",
                        lambda: calls.append("called"))
    restrictions_main.main([])
    assert calls == ["called"]


def test_project_defines_focused_command_scripts() -> None:
    project = Path("pyproject.toml").read_text()
    assert 'highliner-server = "highliner.server.main:main"' in project
    assert 'highliner-etl-density = "highliner.etl.density.main:main"' in project
    assert 'highliner-restrictions = "highliner.restrictions.main:main"' in project
    assert "highliner.cli:main" not in project


def test_chunk_entry_point_declared() -> None:
    project = Path("pyproject.toml").read_text()
    assert 'highliner-etl-chunk = "highliner.etl.chunk.main:main"' in project
