"""Reset every open etl-country issue body to a shared, per-country template."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

_TITLE_RE = re.compile(r"^ETL: (.+)$")

_BODY_TEMPLATE = """
1. Implement the etl for {country} using the skill "adding-country-etls"
2. create the data/ & cache/ folders if doesn't exist
3. Run the complete ETL for that country in a subagent using the `just etl-country {country} 4`
4. While it runs, check that the paralelization is working correctly, if it doesn't stop, fix and re-run
5. Verify the expected output exists under data/
6. Upload to hetzner cloud s3 using `aws s3 cp ./data/{country} s3://highlinescout/`


branch: etl/{country}
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


def _open_issues() -> dict[str, str]:
    """Return every open etl-country issue in the project, title -> url."""
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


def _reset_issue(url: str, country: str) -> None:
    subprocess.run(
        ["gh", "issue", "edit", url, "--body", _BODY_TEMPLATE.format(country=country)],
        check=True, capture_output=True, text=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reset-country-etl-issue-bodies")
    parser.add_argument("--apply", action="store_true",
                        help="edit issue bodies instead of performing a dry run")
    args = parser.parse_args(argv)

    try:
        for title, url in _open_issues().items():
            match = _TITLE_RE.match(title)
            if not match:
                print(f"skipping (title doesn't match 'ETL: <country>'): {title}")
                continue
            country = match.group(1)
            if args.apply:
                _reset_issue(url, country)
                print(f"reset: {country} ({url})")
            else:
                print(f"would reset: {country} ({url})")
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
