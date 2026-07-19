from pathlib import Path

import pytest

from scripts import check_file_length


def test_file_length_check_ignores_missing_and_accepts_files_at_cap(
        tmp_path: Path) -> None:
    at_cap = tmp_path / "at_cap.py"
    at_cap.write_text("line\n" * check_file_length.MAX_LINES)

    assert check_file_length.main([str(tmp_path / "deleted.py"), str(at_cap)]) == 0


def test_file_length_check_reports_longest_files_first(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("line\n" * (check_file_length.MAX_LINES + 1))
    second.write_text("line\n" * (check_file_length.MAX_LINES + 2))

    assert check_file_length.main([str(first), str(second)]) == 1

    output = capsys.readouterr().out
    assert output.index(str(second)) < output.index(str(first))
    assert "2 file(s) over the 500-line cap" in output
