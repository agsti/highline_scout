#!/usr/bin/env bash
set -e
set -euo pipefail

export HETZNER_BUCKET="highlinescout"

mark_busy() {
    printf 'busy' | aws s3 cp - \
        "s3://${HETZNER_BUCKET}/workers/$(hostname)"
}

mark_free() {
    printf 'free' | aws s3 cp - \
        "s3://${HETZNER_BUCKET}/workers/$(hostname)"
}

ISSUE_NUMBER="$1"
SECRETS_FILE="$2"
source $SECRETS_FILE

ISSUE_BODY="$(
    gh issue view "$ISSUE_NUMBER" \
        --json title,body \
        --jq '"# " + .title + "\n\n" + .body'
)"

mark_busy

pi --model "z-ai/glm-5.2" --provider "openrouter" <<EOF
You are implementing GitHub issue #${ISSUE_NUMBER}.
Read AGENTS.md



Your task:
1. Mark the issue as "in-progress" using `
    gh issue edit "$ISSUE_NUMBER" \
        --repo "$GH_REPO" \
        --add-label in-progress \
`
2. Get a fresh copy of the repository using git pull

3. Execute issue:
======== ISSUE START ==========
${ISSUE_BODY}
======== ISSUE END ==========

4. Commit and push your changes to a branch specified in the issue, or make up a branch name
5. Mark the issue as complete, provide a summary of the run in the issue
6. Open a PR, link the issue
7. If there have been any issue, preventing the task to be done, mention the reason in the issue, and label it "blocked"
EOF
mark_free

exit_code=$?

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

