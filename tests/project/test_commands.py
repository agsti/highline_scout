from pathlib import Path


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


def test_justfile_runs_one_country_etl_adapter_per_invocation() -> None:
    justfile = Path("justfile").read_text()

    for family in ("chunk", "density"):
        assert f"etl-{family} country concurrency:" in justfile
        assert f"highliner.etls.{family}.{{{{country}}}}" in justfile

    assert "etl-restriction country:" in justfile
    assert "highliner.etls.restriction.{{country}}" in justfile
