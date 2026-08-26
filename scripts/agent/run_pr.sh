#!/usr/bin/env bash
# Bring a PR up to date with main, get its CI green, then run its "how to run"
# section on a platform and report back on the PR.
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
HEAD_BRANCH="$(gh pr view "$PR" --repo "$GH_REPO" --json headRefName --jq '.headRefName')"
IMAGE="${IMAGE_REPO}:sha-${HEAD_SHA:0:7}"

case "$PLATFORM" in
ovh)
    SCHEDULE_STEP="7. Spawn the job. Use the image from step 6; do not build or pull anything:
   JOB=\$(${SCRIPT_DIR}/platforms/ovh.sh pr-${PR} \$IMAGE \"<command>\" <artifact-path...>)
   Join multiple how-to-run commands into a single shell command with &&.
   The script returns as soon as the job is submitted and prints its id; the
   job then runs on OVH independently of you. Block on it:
   ${SCRIPT_DIR}/platforms/ovh_jobs.sh --wait \"\$JOB\"
   That exits 0 only if the job finished cleanly, and prints where the kept
   artifacts landed. A country ETL runs for hours. If your tooling caps how
   long a single command may run and the wait is cut short, re-run the same
   --wait command — the job is unaffected by your shell dying. Never end your
   turn while the job is still running."
    ;;
*)
    SCHEDULE_STEP="7. Schedule the job. Use the image from step 6; do not build or pull anything:
   ${SCRIPT_DIR}/platforms/${PLATFORM}.sh pr-${PR} \$IMAGE \"<command>\" <artifact-path...>
   Join multiple how-to-run commands into a single shell command with &&.
   The script is synchronous and exits with the job's status."
    ;;
esac

PROMPT="$(
    cat <<EOF
You are running the verification job for GitHub pull request #${PR}.
Read AGENTS.md.

This is a single non-interactive run: nothing will wake you up and no one
will reply to you. Never end your turn to wait for something — if you are
waiting on CI or a job, block on it with a command (gh run watch, the
platform script) rather than stopping. You are done only when you have
commented on the PR in the last step.

Never run docker on this machine — no pull, no build, no run, not even to
check that an image exists or to test a command inside it. The job runs on
${PLATFORM}, which pulls the image from the registry itself, so a local copy
is never needed and each one costs 2.6 GB on a disk that has repeatedly hit
100%. Confirm the image exists the way step 5 describes, from CI's job
status — not by fetching it.

1. Bring branch ${HEAD_BRANCH} up to date with main before anything else.
   A branch that forked before main gained the runner image stage and the
   "Build & push image" job can never produce an image to run, so this is
   not optional and it must happen first:
   - Check it out in an isolated worktree.
   - git fetch origin && git merge origin/main
   - Resolve any conflicts, run the checks in AGENTS.md locally, commit and
     push to ${HEAD_BRANCH}.
   - If main is already merged, say so and move on without an empty commit.

2. Apply any outstanding feedback on the PR before running it. A previous
   run's diagnosis is left as a PR comment, so this is how a fix reaches the
   code — do not skip it because the PR "looks fine".
   gh pr view ${PR} --repo ${GH_REPO} --json comments,reviews
   - Consider every comment and review thread that asks for a change,
     including diagnosis comments a previous run posted (they are titled
     "Failure diagnosis"). Ignore ones already addressed by a later commit,
     and ignore your own pass/fail verdict comments.
   - Judge each on its merits. If a comment is wrong or would break
     something, say so in your reply and do not apply it — you are not
     obliged to agree. If your harness has a skill for receiving code review,
     use it.
   - Apply the ones you accept in the step 1 worktree, run the checks in
     AGENTS.md, commit, and push to ${HEAD_BRANCH}.
   - Reply on the PR listing what you applied, what you rejected and why.
     Never leave a comment silently unaddressed.
   - Do not re-apply a fix that is already in the branch. If nothing is
     outstanding, say so and move on.

3. Read the PR body:
   gh pr view ${PR} --repo ${GH_REPO} --json title,body

4. Extract two things from it:
   - the "how to run" section: the exact commands, in order
   - the "artifacts" section: the repo-relative paths whose outputs must be kept
   If either section is missing, stop, comment on the PR saying which one is
   missing, and exit non-zero. Do not guess.
   Drop any command that does not terminate on its own — a dev server
   (\`just dev\`, \`just dev-web\`, \`npm run dev\`) or anything waiting for
   input would run until the job's timeout expires, billing the whole time
   and producing no verdict. Say in your PR comment which commands you
   dropped.

5. Get CI green on branch ${HEAD_BRANCH}, up to and including the
   "Build & push image" job. That job needs the "check" job to pass first,
   and it only pushes to the registry on branch pushes, not on the
   pull_request event — until it has succeeded there is no image to run.
   - Find the branch's latest run and wait for it:
     gh run list --repo ${GH_REPO} --branch ${HEAD_BRANCH} --limit 1 \\
         --json databaseId,status,conclusion
     gh run watch <run-id> --repo ${GH_REPO} --exit-status
   - If it fails, reproduce the failing step locally in the step 1 worktree
     (AGENTS.md has the commands), fix it, commit, and push to
     ${HEAD_BRANCH}. If your harness has a skill for fixing CI failures,
     use it.
   - Repeat until the "Build & push image" job succeeds on the branch head.
     Give up after 5 failed attempts: comment on the PR with what is still
     failing and exit non-zero. Do not build the image locally as a
     workaround.

6. Resolve the image CI pushed for the current head commit — the merge in
   step 1 and any fixes pushed in steps 2 and 5 change it, so recompute it rather
   than reusing an older tag:
   HEAD_SHA=\$(gh pr view ${PR} --repo ${GH_REPO} --json headRefOid --jq .headRefOid)
   IMAGE=${IMAGE_REPO}:sha-\${HEAD_SHA:0:7}
   At scheduling time head was ${HEAD_SHA:0:7}, i.e. ${IMAGE}.

${SCHEDULE_STEP}

8. If the job did not finish cleanly, diagnose it before reporting. A bare
   log tail is not a diagnosis — the next run acts on what you write here,
   so find the cause.
   ovhai job logs <job-id>
   - Find the root exception, not the wrapper. The chunk ETL reports
     "RuntimeError: chunk X,Y failed"; the cause is the exception above it.
   - Read the exit code. 137 is SIGKILL, which for these jobs means the
     kernel killed it for memory — look for a log that stops mid-run with no
     traceback. Do not treat that as a code exception.
   - Trace it to a specific file and line in the branch, and read that code.
     Say what is actually wrong, not merely what the error text said.
   - Classify it, because the remedy differs:
     * a bug in this PR's code — fix belongs on ${HEAD_BRANCH}
     * a bug in the runner image or shared ETL code — belongs on main, and
       the whole batch is probably hitting it
     * an upstream source problem (403, 404, coverage bounds, an outage)
     * a resource limit — say which, and whether more would actually help
   - Say whether re-running would help. A deterministic failure will fail
     identically; say so rather than suggesting a retry.
   - Never escalate CPU or memory more than once to chase an out-of-memory
     failure. If it dies again at higher memory, that is evidence of a memory
     bug in the code, not of a job that needs a bigger machine — diagnose it
     as such.

9. Report as a PR comment, titled "Failure diagnosis" when the job failed and
   "Verification passed" when it did not. Include: the verdict, how long it
   took, the job id, the image tag, the artifact paths kept, the main merge
   from step 1, what you applied or rejected from step 2, any CI fixes from
   step 5, and — when it failed — the diagnosis from step 8 with the file and
   line, the classification, and whether a re-run would help.
   A later run reads this comment and acts on it, so write the fix plainly
   enough to be applied.
   gh pr comment ${PR} --repo ${GH_REPO} --body "..."

10. Exit with the job's status: 0 only if the job reached a clean terminal
    state. Check the state you actually observed rather than assuming, and do
    not exit 0 because you posted a comment successfully or because the job
    was still running when you stopped watching.
EOF
)"

if [ "${DRY_RUN:-}" = "1" ]; then
    printf '%s\n' "$PROMPT"
    exit 0
fi

printf '%s\n' "$PROMPT" | "$SCRIPT_DIR/agent_call.sh" "$AGENT"
