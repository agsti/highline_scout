#!/usr/bin/env bash
set -euo pipefail

# usage: develop_issue.sh <claude|codex|pi> <issue-number>
AGENT="$1"
ISSUE_NUMBER="$2"

# Honour GH_REPO if set, otherwise use the repo of the current directory.
# Exported so the agent's own `gh` calls target the same repo.
export GH_REPO="${GH_REPO:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"

SCRIPT_DIR="$(dirname "$0")"

ISSUE_BODY="$(
    gh issue view "$ISSUE_NUMBER" \
        --repo "$GH_REPO" \
        --json title,body \
        --jq '"# " + .title + "\n\n" + .body'
)"

exit_code=0
"$SCRIPT_DIR/agent_call.sh" "$AGENT" <<EOF || exit_code=$?
You are implementing GitHub issue #${ISSUE_NUMBER}.
Read AGENTS.md



Your task:
1. Mark the issue as "in-progress" using:
    gh issue edit "$ISSUE_NUMBER" \
        --repo "$GH_REPO" \
        --add-label in-progress

2. call your branch auto/$ISSUE_NUMBER
3. create an isolated worktree at REPO/.worktrees/auto_$ISSUE_NUMBER, switch to it if already exists
4. Do a git pull when starting and get up to date with master or main
5. Fix this issue:
======== ISSUE START ==========
${ISSUE_BODY}
======== ISSUE END ==========

6. Commit and push your changes to the branch
7. Open a PR, link the issue in there
8. In the PR, add a section "how to run" that specifies the exact commands in
   order to try out the new feature. Every command must terminate on its own:
   this section is run unattended on a disposable worker, so a dev server or
   anything else that waits for input never finishes and burns the job's whole
   timeout. Never include `just dev`, `just dev-web`, `npm run dev` or similar.
9. In the PR, add a section "artifacts" listing the repo-relative paths whose
   outputs are worth keeping after the run (e.g. data/italy/). One path per
   line. If the change produces no durable output, write "none".
10. If there have been any issue, preventing the task to be done, mention the reason in the issue, and label it "blocked"
EOF

if [ "$exit_code" -eq 0 ]; then
    gh issue edit "$ISSUE_NUMBER" \
        --repo "$GH_REPO" \
        --add-label completed \
        --remove-label in-progress
else
    gh issue edit "$ISSUE_NUMBER" \
        --repo "$GH_REPO" \
        --add-label failed \
        --remove-label in-progress

    gh issue comment "$ISSUE_NUMBER" \
        --repo "$GH_REPO" \
        --body "Agent exited with status ${exit_code}."
fi
