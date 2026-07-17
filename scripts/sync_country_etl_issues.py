"""Reconcile unfinished country ETLs with open GitHub issues."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_CHECKLIST = re.compile(r"^\s*[-*]\s+\[([^]]+)\]\s+(.+?)\s*$", re.MULTILINE)
_CHECKPOINTS = """- [ ] DTM source and reuse licence selected
- [ ] DTM smoke chunk validated
- [ ] Chunk, density, and applicable restrictions adapters implemented
- [ ] Tests and static checks passed
- [ ] Pull request opened
"""
_OPEN_ISSUES_QUERY = """
query($owner: String!, $name: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    issues(
      first: 100
      after: $endCursor
      states: OPEN
      labels: ["etl-country"]
    ) {
      nodes { title url }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def unfinished_countries(markdown: str) -> list[str]:
    """Return checklist countries whose marker is not the done marker."""
    return [country for marker, country in _CHECKLIST.findall(markdown)
            if marker != "X"]


def _open_issues() -> dict[str, str]:
    result = subprocess.run(
        ["gh", "api", "graphql", "--paginate", "--slurp", "-F",
         "owner={owner}", "-F", "name={repo}", "-f",
         f"query={_OPEN_ISSUES_QUERY}"],
        check=True, capture_output=True, text=True)
    pages = json.loads(result.stdout)
    issues = (
        issue
        for page in pages
        for issue in page["data"]["repository"]["issues"]["nodes"]
    )
    return {issue["title"]: issue["url"] for issue in issues}


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
        countries = dict.fromkeys(unfinished_countries(args.countries_file.read_text()))
        for country in countries:
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
