import tomllib
from pathlib import Path


def test_project_defines_focused_command_scripts() -> None:
    project = Path("pyproject.toml").read_text()
    assert 'highliner-server = "highliner.server.main:main"' in project
    assert ('highliner-etl-density = '
            '"highliner.etls.density.spain.main:main"') in project
    assert ('highliner-restrictions = '
            '"highliner.etls.restriction.spain.main:main"') in project
    assert "highliner.cli:main" not in project


def test_chunk_entry_point_declared() -> None:
    project = Path("pyproject.toml").read_text()
    assert ('highliner-etl-chunk = '
            '"highliner.etls.chunk.spain.main:main"') in project


def test_justfile_runs_one_country_etl_adapter_per_invocation() -> None:
    justfile = Path("justfile").read_text()

    for family in ("chunk", "density"):
        assert f"etl-{family} country concurrency:" in justfile
        assert f"highliner.etls.{family}.{{{{country}}}}" in justfile

    assert "etl-restriction country:" in justfile
    assert "highliner.etls.restriction.{{country}}" in justfile


def test_ci_enforces_python_branch_coverage() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text())
    dev_dependencies = project["project"]["optional-dependencies"]["dev"]
    coverage = project["tool"]["coverage"]

    assert "pytest-cov" in dev_dependencies
    assert coverage["run"] == {
        "branch": True,
        "source": ["highliner", "scripts"],
    }
    assert coverage["report"]["precision"] == 2
    assert coverage["report"]["fail_under"] == 81.10

    workflow = Path(".github/workflows/ci.yml").read_text()
    assert (
        "run: uv run pytest --cov --cov-report= --cov-fail-under=0"
        in workflow
    )
    assert "- name: Check Python coverage" in workflow
    assert "run: uv run coverage report" in workflow
