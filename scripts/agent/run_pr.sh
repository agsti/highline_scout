#!/usr/bin/env bash
# Run a PR's "how to run" section on a platform and report back on the PR.
#
# usage: run_pr.sh <claude|codex|pi> <pr-number> <local|ovh>
#
# Environment:
#   DRY_RUN=1   print the prompt instead of invoking the agent
set -euo pipefail

if [ "$#" -lt 3 ]; then
    echo "usage: run_pr.sh <claude|codex|pi> <pr-number> <local|ovh>" >&2
    exit 2
fi

AGENT="$1"
PR="$2"
PLATFORM="$3"

case "$PLATFORM" in
local | ovh) ;;
*)
    echo "run_pr.sh: unknown platform '${PLATFORM}' (expected local or ovh)" >&2
    exit 2
    ;;
esac

# Honour GH_REPO if set, otherwise use the repo of the current directory.
export GH_REPO="${GH_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"

SCRIPT_DIR="$(dirname "$0")"
IMAGE_REPO="${IMAGE_REPO:-ghcr.io/agsti/highline_scout/runner}"

HEAD_SHA="$(gh pr view "$PR" --repo "$GH_REPO" --json headRefOid --jq '.headRefOid')"
IMAGE="${IMAGE_REPO}:sha-${HEAD_SHA:0:7}"

PROMPT="$(
    cat <<EOF
You are running the verification job for GitHub pull request #${PR}.
Read AGENTS.md.

1. Read the PR body:
   gh pr view ${PR} --repo ${GH_REPO} --json title,body

2. Extract two things from it:
   - the "how to run" section: the exact commands, in order
   - the "artifacts" section: the repo-relative paths whose outputs must be kept
   If either section is missing, stop, comment on the PR saying which one is
   missing, and exit non-zero. Do not guess.

3. Schedule the job. The image is already built by CI; do not build anything:
   ${SCRIPT_DIR}/platforms/${PLATFORM}.sh pr-${PR} ${IMAGE} "<command>" <artifact-path...>
   Join multiple how-to-run commands into a single shell command with &&.
   The script is synchronous and exits with the job's status.

4. Report the outcome as a PR comment: pass or fail, how long it took, the
   artifact paths that were kept, and the tail of the log if it failed.
   gh pr comment ${PR} --repo ${GH_REPO} --body "..."

5. Exit with the job's status.
EOF
)"

if [ "${DRY_RUN:-}" = "1" ]; then
    printf '%s\n' "$PROMPT"
    exit 0
fi

printf '%s\n' "$PROMPT" | "$SCRIPT_DIR/agent_call.sh" "$AGENT"
