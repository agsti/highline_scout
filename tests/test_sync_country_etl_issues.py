"""Tests for reconciling unfinished country ETLs with GitHub issues."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "sync_country_etl_issues",
    Path(__file__).parent.parent / "scripts" / "sync_country_etl_issues.py",
)
assert _SPEC is not None and _SPEC.loader is not None
sync = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sync)


def test_unfinished_countries_excludes_only_done_entries() -> None:
    markdown = "- [ ] Albania\n- [X] Spain\n- [P] France\n"

    assert sync.unfinished_countries(markdown) == ["Albania", "France"]


def test_dry_run_lists_issues_without_creating_them(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    countries = tmp_path / "COUNTRIES.md"
    countries.write_text("- [ ] Albania\n")
    calls: list[list[str]] = []

    def fake_run(
            command: list[str], **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "[]", "")

    monkeypatch.setattr(sync.subprocess, "run", fake_run)

    assert sync.main(["--countries-file", str(countries)]) == 0
    assert calls == [["gh", "issue", "list", "--state", "open", "--label",
                      "etl-country", "--json", "title,url", "--limit", "1000"]]
    assert "would create: ETL: Albania" in capsys.readouterr().out


def test_apply_skips_existing_titles_and_creates_missing_issue(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    countries = tmp_path / "COUNTRIES.md"
    countries.write_text("- [ ] Albania\n- [ ] France\n")
    calls: list[list[str]] = []

    def fake_run(
            command: list[str], **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[2] == "list":
            return subprocess.CompletedProcess(
                command, 0, '[{"title": "ETL: France", "url": "https://example/2"}]',
                "")
        return subprocess.CompletedProcess(command, 0, "https://example/1\n", "")

    monkeypatch.setattr(sync.subprocess, "run", fake_run)

    assert sync.main(["--countries-file", str(countries), "--apply"]) == 0
    assert [call[2] for call in calls] == ["list", "create"]
    assert calls[1][calls[1].index("--title") + 1] == "ETL: Albania"
    assert "etl-country" in calls[1]
    body = calls[1][calls[1].index("--body") + 1]
    assert body.count("- [ ]") == 5
    assert "already exists: https://example/2" in capsys.readouterr().out


def test_gh_failure_returns_one_and_reports_the_error(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    countries = tmp_path / "COUNTRIES.md"
    countries.write_text("- [ ] Albania\n")

    def failing_run(
            command: list[str], **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, command, stderr="not authenticated")

    monkeypatch.setattr(sync.subprocess, "run", failing_run)

    assert sync.main(["--countries-file", str(countries)]) == 1
    assert "not authenticated" in capsys.readouterr().err
