from pathlib import Path

import pytest
from highliner.etls.density import shared, spain
from highliner.etls.restriction import spain as restrictions_main
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



def test_density_discovers_only_grid_regions_in_country(tmp_path: Path) -> None:
    (tmp_path / "spain" / "a").mkdir(parents=True)
    (tmp_path / "spain" / "a" / "grid.json").write_text("{}")
    (tmp_path / "spain" / "scratch").mkdir()
    (tmp_path / "france" / "b").mkdir(parents=True)
    (tmp_path / "france" / "b" / "grid.json").write_text("{}")

    assert shared.discover_regions(tmp_path, "spain") == [tmp_path / "spain" / "a"]


def test_spain_density_adapter_has_no_region_argument(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(spain.shared, "build_country_density",
                        fake)
    spain.main(["--data-dir", "/tmp/data", "--workers", "3"])
    assert calls == [{"country": "spain", "data_dir": Path("/tmp/data"),
                      "workers": 3}]


def test_density_progress_lines_are_prefixed_and_newline_terminated(
        capsys: pytest.CaptureFixture[str]) -> None:
    report = shared._make_reporter("aragon", clock=iter([0.0, 1.0]).__next__)
    report(3, 10)
    out = capsys.readouterr().out
    assert out == "[aragon] pairs file 3/10 (30.0%)  elapsed 0:00:01\n"


def test_density_progress_throttles_between_first_and_final(
        capsys: pytest.CaptureFixture[str]) -> None:
    ticks = iter([0.0, 1.0, 2.0, 40.0, 41.0])
    report = shared._make_reporter("aragon", interval=30.0, clock=ticks.__next__)
    report(1, 10)   # first call always prints
    report(2, 10)   # 1s later: throttled
    report(3, 10)   # 40s in: interval elapsed, prints
    report(10, 10)  # final call always prints
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[3] for line in lines] == ["1/10", "3/10", "10/10"]


def test_restrictions_command_builds_layers(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(restrictions_main, "download_sources",
                        lambda raw_dir: calls.append(raw_dir))
    monkeypatch.setattr(restrictions_main.shared, "write_layers",
                        lambda *args, **kwargs: {})
    restrictions_main.main(["--data-dir", str(tmp_path)])
    assert calls == [tmp_path / "spain" / "restrictions" / "raw"]


def test_project_defines_focused_command_scripts() -> None:
    project = Path("pyproject.toml").read_text()
    assert 'highliner-server = "highliner.server.main:main"' in project
    assert 'highliner-etl-density = "highliner.etls.density.spain:main"' in project
    assert ('highliner-restrictions = '
            '"highliner.etls.restriction.spain:main"') in project
    assert "highliner.cli:main" not in project


def test_chunk_entry_point_declared() -> None:
    project = Path("pyproject.toml").read_text()
    assert 'highliner-etl-chunk = "highliner.etls.chunk.spain:main"' in project


def test_justfile_runs_country_etl_adapters_sequentially() -> None:
    justfile = Path("justfile").read_text()

    assert 'ETL_COUNTRIES := "spain"' in justfile
    for family in ("chunk", "density", "restriction"):
        assert f"etl-{family}-8:" in justfile or f"etl-{family}:" in justfile
        assert f"highliner.etls.{family}.$country" in justfile
