#!/usr/bin/env bash
# Run develop_issue.sh over every open issue that is not labelled "blocked".
#
# usage: process_issues.sh <claude|codex|pi>
set -euo pipefail

AGENT="$1"

# Honour GH_REPO if set, otherwise use the repo of the current directory.
export GH_REPO="${GH_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"

SCRIPT_DIR="$(dirname "$0")"

ISSUES="$(
    gh issue list \
        --repo "$GH_REPO" \
        --state open \
        --limit 500 \
        --json number,labels \
        --jq '.[] | select([.labels[].name] | index("blocked") | not) | .number'
)"

if [ -z "$ISSUES" ]; then
    echo "No open issues to process."
    exit 0
fi

echo "Processing issues:" $ISSUES

failed=()
for issue in $ISSUES; do
    echo "=== Issue #${issue} ($AGENT) ==="
    if ! "$SCRIPT_DIR/develop_issue.sh" "$AGENT" "$issue"; then
        echo "=== Issue #${issue} failed, continuing ==="
        failed+=("$issue")
    fi
done

if [ "${#failed[@]}" -gt 0 ]; then
    echo "Failed issues: ${failed[*]}"
    exit 1
fi

echo "All issues processed."
