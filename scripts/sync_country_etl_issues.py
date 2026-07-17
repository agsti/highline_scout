"""Reconcile unfinished country ETLs with open GitHub issues."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_CHECKLIST = re.compile(r"^\s*[-*]\s+\[([^]])\]\s+(.+?)\s*$", re.MULTILINE)
_CHECKPOINTS = """- [ ] DTM source and reuse licence selected
- [ ] DTM smoke chunk validated
- [ ] Chunk, density, and applicable restrictions adapters implemented
- [ ] Tests and static checks passed
- [ ] Pull request opened
"""


def unfinished_countries(markdown: str) -> list[str]:
    """Return checklist countries whose marker is not the done marker."""
    return [country for marker, country in _CHECKLIST.findall(markdown)
            if marker != "X"]


def _open_issues() -> dict[str, str]:
    result = subprocess.run(
        ["gh", "issue", "list", "--state", "open", "--label", "etl-country",
         "--json", "title,url", "--limit", "1000"],
        check=True, capture_output=True, text=True)
    return {issue["title"]: issue["url"] for issue in json.loads(result.stdout)}


def _create_issue(title: str) -> str:
    result = subprocess.run(
        ["gh", "issue", "create", "--title", title, "--label", "etl-country",
         "--body", _CHECKPOINTS],
        check=True, capture_output=True, text=True)
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sync-country-etl-issues")
    parser.add_argument("--countries-file", type=Path, default=Path("COUNTRIES.md"))
    parser.add_argument("--apply", action="store_true",
                        help="create missing issues instead of performing a dry run")
    args = parser.parse_args(argv)

    try:
        existing = _open_issues()
        for country in unfinished_countries(args.countries_file.read_text()):
            title = f"ETL: {country}"
            if title in existing:
                print(f"already exists: {existing[title]}")
            elif args.apply:
                print(f"created: {_create_issue(title)}")
            else:
                print(f"would create: {title}")
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
