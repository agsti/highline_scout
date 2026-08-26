#!/usr/bin/env bash
# One line per PR being run by run_prs.sh: where each one actually is.
#
# usage: prs_status.sh [pr-number...]
#
# With no arguments, reports every PR that has a log under $LOG_DIR.
#
# The driver's per-PR log stays empty until that agent exits — `claude --print`
# buffers — so this reads the states that do move: the agent process, CI on the
# PR's branch, the OVH job, and whether a verdict comment has landed.
#
# Environment:
#   LOG_DIR  where run_prs.sh writes per-PR logs (default: .runs/prs)
set -euo pipefail

LOG_DIR="${LOG_DIR:-.runs/prs}"
export GH_REPO="${GH_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
TERMINAL_RE='^(DONE|FAILED|ERROR|TIMEOUT|INTERRUPTED|SYNC_FAILED)$'

if [ "$#" -gt 0 ]; then
    PRS=("$@")
else
    mapfile -t PRS < <(find "$LOG_DIR" -name '*.log' -printf '%f\n' 2>/dev/null \
        | sed 's/\.log$//' | sort -n)
fi

if [ "${#PRS[@]}" -eq 0 ]; then
    echo "no PR logs under $LOG_DIR" >&2
    exit 1
fi

# One query for every job, rather than one per PR.
JOBS="$(ovhai job list --all --output json)"

printf '%-4s %-9s %-9s %-18s %-14s %s\n' \
    PR BRANCH AGENT CI JOB VERDICT

for pr in "${PRS[@]}"; do
    branch="$(gh pr view "$pr" --repo "$GH_REPO" --json headRefName --jq .headRefName 2>/dev/null || echo '?')"

    if pgrep -f "run_pr.sh .* $pr ovh" >/dev/null 2>&1; then
        agent="running"
    elif [ -f "$LOG_DIR/$pr.status" ]; then
        code="$(cat "$LOG_DIR/$pr.status")"
        [ "$code" = "0" ] && agent="pass" || agent="exit $code"
    else
        agent="-"
    fi

    ci="$(gh run list --repo "$GH_REPO" --branch "$branch" --limit 1 \
        --json status,conclusion --jq '.[0] | "\(.status)/\(.conclusion // "…")"' 2>/dev/null || echo '?')"

    job="$(printf '%s' "$JOBS" | jq -r --arg n "run-pr-$pr" '
        [.[] | select(.spec.name == $n)] | sort_by(.status.queuedAt) | last
        | if . == null then "-" else .status.state end')"

    # A verdict is the agent's own comment; show how long ago it landed.
    verdict="$(gh pr view "$pr" --repo "$GH_REPO" --json comments \
        --jq '[.comments[] | select(.body | test("Verification"; "i"))] | last
              | if . == null then "-" else .createdAt end' 2>/dev/null || echo '-')"

    printf '%-4s %-9s %-9s %-18s %-14s %s\n' \
        "$pr" "$branch" "$agent" "$ci" "$job" "$verdict"
done

echo
printf 'quota: '
"$(dirname "$0")/platforms/ovh_jobs.sh" --free-cpu | tr -d '\n'
echo " CPU free"
