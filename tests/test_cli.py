from pathlib import Path

import pytest
from highliner.etls.chunk import main as chunk_main
from highliner.etls.density import main as density_main
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

    def fake(country: str, region: str, bbox: tuple[float, ...], data_dir: Path,
             **kwargs: object) -> int:
        calls.update(country=country, region=region, bbox=bbox, data_dir=data_dir,
                     **kwargs)
        return 1

    monkeypatch.setattr("highliner.etls.chunk.shared.precompute", fake)
    chunk_main.main(["--region", "catalonia", "--data-dir", "/tmp/x",
                     "--bbox", "0,0,10000,10000", "--chunk-km", "10",
                     "--workers", "4"])
    assert calls["region"] == "catalonia"
    assert calls["country"] == "spain"
    assert calls["bbox"] == (0.0, 0.0, 10000.0, 10000.0)
    assert calls["chunk_m"] == 10000.0
    assert calls["crs"] == "EPSG:25831"
    assert calls["dtm_source"] == "icgc"
    assert calls["workers"] == 4


def test_density_command_uses_region_directory(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake(region_dir: Path, **kwargs: object) -> int:
        calls.update(region_dir=region_dir, **kwargs)
        return 7

    monkeypatch.setattr("highliner.etls.density.main.builder.build_density", fake)
    density_main.main(["--region", "catalonia", "--data-dir", "/tmp/x"])
    assert calls["region_dir"] == Path("/tmp/x") / "spain" / "catalonia"


def test_density_command_forwards_country(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake(region_dir: Path, **kwargs: object) -> int:
        calls.update(region_dir=region_dir, **kwargs)
        return 7

    monkeypatch.setattr("highliner.etls.density.main.builder.build_density", fake)
    density_main.main(["--region", "catalonia", "--country", "france",
                       "--data-dir", "/tmp/x"])
    assert calls["region_dir"] == Path("/tmp/x") / "france" / "catalonia"
    assert calls["restrictions_dir"] == Path("/tmp/x") / "france" / "restrictions"


def test_density_command_forwards_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake(region_dir: Path, **kwargs: object) -> int:
        calls.update(region_dir=region_dir, **kwargs)
        return 7

    monkeypatch.setattr("highliner.etls.density.main.builder.build_density", fake)
    density_main.main(["--region", "catalonia", "--workers", "3"])
    assert calls["workers"] == 3


def test_density_progress_lines_are_prefixed_and_newline_terminated(
        capsys: pytest.CaptureFixture[str]) -> None:
    report = density_main._make_reporter("aragon", clock=iter([0.0, 1.0]).__next__)
    report(3, 10)
    out = capsys.readouterr().out
    assert out == "[aragon] pairs file 3/10 (30.0%)  elapsed 0:00:01\n"


def test_density_progress_throttles_between_first_and_final(
        capsys: pytest.CaptureFixture[str]) -> None:
    ticks = iter([0.0, 1.0, 2.0, 40.0, 41.0])
    report = density_main._make_reporter("aragon", interval=30.0,
                                         clock=ticks.__next__)
    report(1, 10)   # first call always prints
    report(2, 10)   # 1s later: throttled
    report(3, 10)   # 40s in: interval elapsed, prints
    report(10, 10)  # final call always prints
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[3] for line in lines] == ["1/10", "3/10", "10/10"]


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
    assert 'highliner-etl-density = "highliner.etls.density.main:main"' in project
    assert 'highliner-restrictions = "highliner.restrictions.main:main"' in project
    assert "highliner.cli:main" not in project


def test_chunk_entry_point_declared() -> None:
    project = Path("pyproject.toml").read_text()
    assert 'highliner-etl-chunk = "highliner.etls.chunk.main:main"' in project
