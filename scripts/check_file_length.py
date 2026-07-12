"""Fail if any tracked Python file exceeds MAX_LINES.

Ruff has no file-length rule (pylint's too-many-lines is unimplemented), so the
500-line cap enforced in CI and pre-commit lives here. Paths may be passed as
arguments (pre-commit does this); with none, every tracked .py file is checked.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MAX_LINES = 500


def _tracked_python_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "*.py"], check=True,
                         capture_output=True, text=True).stdout
    return [Path(line) for line in out.splitlines() if line]


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or _tracked_python_files()
    too_long = []
    for path in paths:
        if not path.exists():
            continue
        n = len(path.read_text().splitlines())
        if n > MAX_LINES:
            too_long.append((path, n))

    for path, n in sorted(too_long, key=lambda t: -t[1]):
        print(f"{path}:1: file too long ({n} > {MAX_LINES} lines)")
    if too_long:
        print(f"\n{len(too_long)} file(s) over the {MAX_LINES}-line cap; "
              f"split them into focused modules.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
