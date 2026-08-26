#!/usr/bin/env bash
# Run many PRs' verification jobs on OVH, as concurrently as the quota allows.
#
# usage:
#   run_prs.sh <claude|codex|pi> [pr-number...]
#
# With no PR numbers, every open PR that carries both a "how to run" and an
# "artifacts" section is queued; PRs missing either are listed and skipped
# rather than guessed at.
#
# One run_pr.sh per PR runs in the background, each writing to
# .runs/prs/<pr>.log. Local parallelism is capped by JOBS, and each job waits
# for OVH quota room instead of bouncing off an over-quota rejection.
#
# Environment:
#   JOBS         how many PRs to work at once (default: quota / OVH_CPU)
#   OVH_CPU      CPUs per OVH job (default: 8; 4 GiB RAM each, max 12)
#   OVH_WAIT_CAPACITY  seconds a job waits for quota room (default: 3h)
#   OVH_ENV      space-separated env var names to forward into every job, for
#                the API keys some countries' sources need. A PR whose commands
#                need a key you have not set is skipped rather than failed
#                slowly on the worker.
#   DRY_RUN=1    print the plan and exit without launching anything
set -euo pipefail

AGENT="${1:-}"
case "$AGENT" in
claude | codex | pi) shift ;;
*)
    echo "usage: run_prs.sh <claude|codex|pi> [pr-number...]" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(dirname "$0")"
export GH_REPO="${GH_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
export OVH_CPU="${OVH_CPU:-8}"
export OVH_WAIT_CAPACITY="${OVH_WAIT_CAPACITY:-10800}"
LOG_DIR="${LOG_DIR:-.runs/prs}"

pr_body() { gh pr view "$1" --repo "$GH_REPO" --json body --jq .body; }

has_both_sections() {
    local body
    body="$(pr_body "$1")"
    grep -qi '^## *how to run' <<<"$body" && grep -qi '^## *artifacts' <<<"$body"
}

# Some countries' DTM or restriction sources need an API key, which the PR
# body declares as `export HIGHLINER_..._API_KEY=...`. Catch a missing one here
# rather than after an agent has spent an hour getting CI green.
missing_secrets() {
    local body name missing=""
    body="$(pr_body "$1")"
    while read -r name; do
        [ -z "$name" ] && continue
        if [ -z "${!name:-}" ]; then
            missing="$missing $name"
        fi
    done < <(grep -oE '^export [A-Z_][A-Z0-9_]*' <<<"$body" | awk '{print $2}' | sort -u)
    echo "${missing# }"
}

# Explicit numbers are taken as given; a bare invocation discovers the work.
if [ "$#" -gt 0 ]; then
    CANDIDATES=("$@")
else
    mapfile -t CANDIDATES < <(gh pr list --repo "$GH_REPO" --state open \
        --limit 100 --json number --jq '.[].number')
fi

PRS=()
SKIPPED=()
NEEDS_SECRET=()
FORWARD=""
for pr in "${CANDIDATES[@]}"; do
    if ! has_both_sections "$pr"; then
        SKIPPED+=("$pr")
        continue
    fi
    missing="$(missing_secrets "$pr")"
    if [ -n "$missing" ]; then
        NEEDS_SECRET+=("$pr:$missing")
        continue
    fi
    # A key the PR needs and you do have must be forwarded into the job.
    for name in $(grep -oE '^export [A-Z_][A-Z0-9_]*' <<<"$(pr_body "$pr")" \
        | awk '{print $2}' | sort -u); do
        case " $FORWARD " in *" $name "*) ;; *) FORWARD="$FORWARD $name" ;; esac
    done
    PRS+=("$pr")
done
export OVH_ENV="${OVH_ENV:-}${FORWARD}"

QUOTA="$(ovhai me --output json | jq -r '.quotas.resources.CPU')"
SLOTS=$((QUOTA / OVH_CPU))
[ "$SLOTS" -lt 1 ] && SLOTS=1
# More local agents than OVH slots is deliberate: an agent spends most of its
# life merging main and waiting on CI, holding no OVH quota at all.
JOBS="${JOBS:-$SLOTS}"

echo "repo:      $GH_REPO"
echo "agent:     $AGENT"
echo "queued:    ${#PRS[@]} PR(s): ${PRS[*]:-none}"
[ "${#SKIPPED[@]}" -gt 0 ] &&
    echo "skipped:   ${SKIPPED[*]} (missing a how-to-run or artifacts section)"
if [ "${#NEEDS_SECRET[@]}" -gt 0 ]; then
    echo "blocked:   ${NEEDS_SECRET[*]}"
    echo "           set those in your shell and re-run to include them"
fi
[ -n "${OVH_ENV// /}" ] && echo "forwarding:${OVH_ENV}"
echo "quota:     $QUOTA CPU / $OVH_CPU per job = $SLOTS concurrent OVH job(s)"
echo "local:     $JOBS agent(s) at once, logs under $LOG_DIR/"

if [ "${#PRS[@]}" -eq 0 ]; then
    echo "nothing to run" >&2
    exit 1
fi

if [ "${DRY_RUN:-}" = "1" ]; then
    echo "(dry run: nothing launched)"
    exit 0
fi

mkdir -p "$LOG_DIR"
declare -A STATUS=()
running=0

for pr in "${PRS[@]}"; do
    while [ "$running" -ge "$JOBS" ]; do
        wait -n || true
        running=$((running - 1))
    done
    echo "launching PR $pr -> $LOG_DIR/$pr.log"
    # set +e inside the subshell: under errexit a failing run_pr.sh would kill
    # the subshell before the status file was written, losing the exit code of
    # exactly the runs worth reporting.
    (
        set +e
        "$SCRIPT_DIR/run_pr.sh" "$AGENT" "$pr" ovh >"$LOG_DIR/$pr.log" 2>&1
        echo "$?" >"$LOG_DIR/$pr.status"
    ) &
    running=$((running + 1))
done
wait

echo
echo "PR   RESULT"
FAILED=0
for pr in "${PRS[@]}"; do
    code="$(cat "$LOG_DIR/$pr.status" 2>/dev/null || echo "?")"
    if [ "$code" = "0" ]; then
        printf '%-4s pass\n' "$pr"
    else
        printf '%-4s FAIL (exit %s, see %s/%s.log)\n' "$pr" "$code" "$LOG_DIR" "$pr"
        FAILED=$((FAILED + 1))
    fi
done
echo
echo "$((${#PRS[@]} - FAILED))/${#PRS[@]} passed"
[ "$FAILED" -eq 0 ]
