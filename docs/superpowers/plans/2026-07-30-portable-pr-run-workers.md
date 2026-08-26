# Portable PR-run workers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a PR's "how to run" commands on disposable cloud capacity from a CI-built image, keep the declared outputs, and report the verdict back to the PR.

**Architecture:** Three layers. CI builds a `runner` image per commit whose entrypoint runs one command and copies declared paths to an artifact mount. Thin per-platform scripts (`local.sh`, `ovh.sh`) schedule that image and share one calling convention. A local orchestrator agent resolves a PR to its image tag, reads the how-to-run and artifacts sections from the PR body, invokes a platform script, and comments the result.

**Tech Stack:** Bash, Docker/Buildx, GitHub Actions, GHCR, OVHcloud AI Training (`ovhai`), `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-07-30-portable-pr-run-workers-design.md`

## Global Constraints

- All scripts are `bash` with `set -euo pipefail`, matching the style of the existing `scripts/agent/*.sh`.
- No unit tests for shell scripts. Every task is verified by running the thing it built and checking the observable result — exit status, files on disk, job state.
- Image reference: `ghcr.io/agsti/highline_scout/runner`, pinned by the immutable `sha-<short>` tag. Never the branch tag.
- Entrypoint contract: positional `<command>`; environment `RUN_ID`, `ARTIFACTS` (newline-separated repo-relative paths), `ARTIFACT_DIR` (default `/artifacts`).
- Platform script contract: `<run-id> <image> <command> [artifact-path...]`, synchronous, exits with the job's status.
- The runner image contains no agent CLI, no LLM API key, no `gh`, and no GitHub token.
- Run `bash -n <script>` on every shell script before committing it.

---

## File Structure

| File | Responsibility |
|---|---|
| `docs/superpowers/notes/2026-07-30-ovh-ai-training-probe.md` | Measured OVH facts (UID, disk, CLI syntax) that later tasks depend on |
| `scripts/runner/entrypoint.sh` | Run one command, collect declared artifacts + log. Lives in the image |
| `Dockerfile` | Adds a `runner` stage on top of the existing builder |
| `.github/workflows/ci.yml` | Adds a build-push step for the `runner` target |
| `scripts/agent/platforms/local.sh` | Schedule a job via `docker run` |
| `scripts/agent/platforms/ovh.sh` | Schedule a job via `ovhai job run`, poll to completion |
| `scripts/agent/run_pr.sh` | Local orchestrator: PR → image + sections → platform script → PR comment |
| `scripts/agent/develop_issue.sh` | Gains the artifacts-section instruction in its prompt |

---

### Task 1: Probe OVH AI Training and record the facts

The spec lists three unverified facts that decide the Dockerfile's user, where `data/` can live, and the exact `ovhai` syntax Task 5 hardcodes. Settle them with a throwaway job before writing code against guesses.

**Files:**
- Create: `docs/superpowers/notes/2026-07-30-ovh-ai-training-probe.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the measured values Tasks 2 and 5 read — container UID, writable paths, local disk GB at a given `--cpu`, the exact `ovhai job run` flag spelling, the JSON field holding a job's id and terminal state.

- [ ] **Step 1: Install and authenticate the CLI**

```bash
curl -s https://cli.bhs.ai.cloud.ovh.net/install.sh | bash
ovhai login
ovhai me
```

Expected: `ovhai me` prints your user without error. `ovhai login` is interactive — run it yourself with `! ovhai login` if needed.

- [ ] **Step 2: Run the probe job**

```bash
ovhai job run --cpu 4 --name probe-1 ubuntu:24.04 -- \
  bash -c 'id; echo ---; df -h /; echo ---; nproc; free -g; echo ---; touch /artifacts/x 2>&1 || echo "/artifacts not writable"'
```

- [ ] **Step 3: Read the logs and record the answers**

```bash
ovhai job list
ovhai job logs <job-id>
```

Record verbatim in the notes file: the `uid`/`gid` from `id`, the root filesystem size from `df -h`, memory from `free -g`, and whether `/artifacts` was writable without a volume attached.

- [ ] **Step 4: Probe volume attachment**

Create an Object Storage bucket in the same region as the job, then:

```bash
ovhai job run --cpu 1 --name probe-2 \
  --volume <bucket>@<region>:/artifacts:rw \
  ubuntu:24.04 -- bash -c 'touch /artifacts/hello && ls -la /artifacts'
```

Record: the exact accepted `--volume` syntax, and whether the write succeeded under the UID from Step 3.

- [ ] **Step 5: Record the machine-readable job interface**

```bash
ovhai job get <job-id> --output json | head -40
```

Record the JSON path to the job id and to its terminal state, plus the exact terminal state strings observed (e.g. `DONE`, `FAILED`). Task 5 parses these.

- [ ] **Step 6: Confirm billing source**

Check in the OVHcloud control panel that the probe jobs were billed against trial credits rather than a payment method. Record yes/no. If no, stop and raise it — the whole approach assumes credits cover AI Training.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/notes/2026-07-30-ovh-ai-training-probe.md
git commit -m "docs: record measured OVH AI Training job facts"
```

---

### Task 2: Runner entrypoint and Dockerfile stage

**Files:**
- Create: `scripts/runner/entrypoint.sh`
- Modify: `Dockerfile` (append a new stage after the existing final stage)

**Interfaces:**
- Consumes: the UID finding from Task 1.
- Produces: build target `runner`, entrypoint `/app/entrypoint.sh`, writing to `$ARTIFACT_DIR/runs/$RUN_ID/` — `run.log` plus each declared path at its original relative position.

- [ ] **Step 1: Write the entrypoint**

Create `scripts/runner/entrypoint.sh`:

```bash
#!/usr/bin/env bash
# Runner image entrypoint: run one command, keep the declared artifacts.
#
# usage: entrypoint.sh <command>
#
# Environment:
#   RUN_ID        opaque label for this run (default: UTC timestamp)
#   ARTIFACTS     newline-separated repo-relative paths to keep
#   ARTIFACT_DIR  where to keep them (default: /artifacts)
set -uo pipefail

ARTIFACT_DIR="${ARTIFACT_DIR:-/artifacts}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%d-%H%M%S)}"
ARTIFACTS="${ARTIFACTS:-}"
DEST="$ARTIFACT_DIR/runs/$RUN_ID"

collect_artifacts() {
    local path parent
    while IFS= read -r path; do
        [ -z "$path" ] && continue
        if [ ! -e "$path" ]; then
            echo "runner: declared artifact '$path' does not exist, skipping" >&2
            continue
        fi
        parent="$(dirname "$path")"
        mkdir -p "$DEST/$parent"
        cp -r "$path" "$DEST/$parent/"
    done <<< "$ARTIFACTS"
    return 0
}

if [ "$#" -lt 1 ]; then
    echo "usage: entrypoint.sh <command>" >&2
    exit 2
fi

mkdir -p "$DEST"
trap collect_artifacts EXIT

bash -lc "$*" 2>&1 | tee "$DEST/run.log"
exit "${PIPESTATUS[0]}"
```

- [ ] **Step 2: Verify it syntax-checks and behaves**

```bash
bash -n scripts/runner/entrypoint.sh
chmod +x scripts/runner/entrypoint.sh
d="$(mktemp -d)"
RUN_ID=t1 ARTIFACT_DIR="$d" ARTIFACTS="out" \
  scripts/runner/entrypoint.sh 'mkdir -p out && echo hi > out/f && exit 3'
echo "exit=$?"
cat "$d/runs/t1/out/f"; ls "$d/runs/t1"
```

Expected: `exit=3`; `out/f` contains `hi` despite the non-zero exit (the trap fired); `run.log` exists alongside it.

- [ ] **Step 3: Verify a missing declared path warns without aborting**

```bash
d="$(mktemp -d)"
RUN_ID=t2 ARTIFACT_DIR="$d" ARTIFACTS="$(printf 'out\nnope')" \
  scripts/runner/entrypoint.sh 'mkdir -p out && echo hi > out/f'
echo "exit=$?"
ls "$d/runs/t2/out"
```

Expected: `exit=0`, a warning naming `nope` on stderr, and `out/f` still collected.

- [ ] **Step 4: Append the runner stage to the Dockerfile**

```dockerfile
# --- ETL/command runner -------------------------------------------------
FROM python:3.12-slim-bookworm AS runner

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl git unar \
    && curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh \
        | bash -s -- --to /usr/local/bin \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY highliner ./highliner
COPY justfile pyproject.toml ./
COPY scripts/runner/entrypoint.sh /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN mkdir -p /artifacts && chmod 0777 /artifacts

ENTRYPOINT ["/app/entrypoint.sh"]
```

Leave the stage running as root — no `USER` line — so the entrypoint can write whatever UID AI Training imposes. Note that decision in the probe notes.

- [ ] **Step 5: Build and run the image**

```bash
docker build --target runner -t highline-runner:test .
d="$(mktemp -d)"
docker run --rm \
  -e RUN_ID=t3 -e ARTIFACTS='out' -e ARTIFACT_DIR=/artifacts \
  -v "$d:/artifacts" \
  highline-runner:test 'mkdir -p out && just --version > out/just.txt'
cat "$d/runs/t3/out/just.txt"
```

Expected: prints a `just` version, proving `just` is installed and artifacts survive the container.

- [ ] **Step 6: Verify the server image still builds unchanged**

```bash
docker build -t highline-server:test .
```

Expected: succeeds and still selects the server stage by default — the runner stage must not become the implicit final stage. If it did, move the runner stage above the server stage.

- [ ] **Step 7: Commit**

```bash
git add scripts/runner/entrypoint.sh Dockerfile
git commit -m "feat(runner): add job entrypoint and runner image stage"
```

---

### Task 3: Publish the runner image from CI

**Files:**
- Modify: `.github/workflows/ci.yml:148-189` (the `docker` job)

**Interfaces:**
- Consumes: the `runner` build target from Task 2.
- Produces: `ghcr.io/agsti/highline_scout/runner:sha-<short>` on every pushed branch that passes `check`.

- [ ] **Step 1: Add runner metadata and build steps to the `docker` job**

Append to the job's `steps`, after the existing build-and-push step:

```yaml
      - name: Runner image metadata
        id: meta-runner
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}/runner
          tags: |
            type=ref,event=branch
            type=sha
            type=raw,value=latest,enable={{is_default_branch}}

      - name: Build and push runner
        uses: docker/build-push-action@v6
        with:
          context: .
          target: runner
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta-runner.outputs.tags }}
          labels: ${{ steps.meta-runner.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: build and push the runner image"
git push -u origin HEAD
```

- [ ] **Step 3: Watch the run**

```bash
gh run watch "$(gh run list --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Expected: the `docker` job succeeds and both build-push steps run.

- [ ] **Step 4: Confirm the published tag**

```bash
gh api "/users/agsti/packages/container/highline_scout%2Frunner/versions" \
  --jq '.[0].metadata.container.tags'
git rev-parse --short HEAD
```

Expected: the tag list includes `sha-` followed by that short SHA.

- [ ] **Step 5: Make the package public**

In the GitHub UI, set the `highline_scout/runner` package visibility to public so OVH pulls need no credentials. Verify anonymously:

```bash
docker logout ghcr.io
docker pull ghcr.io/agsti/highline_scout/runner:sha-$(git rev-parse --short HEAD)
```

Expected: pull succeeds without login.

---

### Task 4: Local platform script

**Files:**
- Create: `scripts/agent/platforms/local.sh`

**Interfaces:**
- Consumes: the entrypoint contract from Task 2.
- Produces: `platforms/local.sh <run-id> <image> <command> [artifact-path...]`, exiting with the container's status.

- [ ] **Step 1: Write the script**

Create `scripts/agent/platforms/local.sh`:

```bash
#!/usr/bin/env bash
# Schedule a runner job on this machine via docker.
#
# usage: local.sh <run-id> <image> <command> [artifact-path...]
#
# Environment:
#   ARTIFACT_ROOT  host directory that receives runs/ (default: $PWD/.runs)
set -euo pipefail

ARTIFACT_ROOT="${ARTIFACT_ROOT:-$PWD/.runs}"

if [ "$#" -lt 3 ]; then
    echo "usage: local.sh <run-id> <image> <command> [artifact-path...]" >&2
    exit 2
fi

RUN_ID="$1"
IMAGE="$2"
COMMAND="$3"
shift 3

ARTIFACTS=""
if [ "$#" -gt 0 ]; then
    ARTIFACTS="$(printf '%s\n' "$@")"
fi

mkdir -p "$ARTIFACT_ROOT"

exec docker run --rm \
    -e "RUN_ID=$RUN_ID" \
    -e "ARTIFACTS=$ARTIFACTS" \
    -e "ARTIFACT_DIR=/artifacts" \
    -v "$ARTIFACT_ROOT:/artifacts" \
    "$IMAGE" "$COMMAND"
```

- [ ] **Step 2: Verify argument handling**

```bash
bash -n scripts/agent/platforms/local.sh
chmod +x scripts/agent/platforms/local.sh
scripts/agent/platforms/local.sh pr-7 img:tag; echo "exit=$?"
```

Expected: usage message, `exit=2`.

- [ ] **Step 3: Verify a real run against the image from Task 2**

```bash
ARTIFACT_ROOT="$(mktemp -d)" scripts/agent/platforms/local.sh \
  pr-test highline-runner:test 'mkdir -p out && echo ok > out/f' out
echo "exit=$?"
```

Expected: `exit=0`, and `runs/pr-test/out/f` plus `runs/pr-test/run.log` exist under that `ARTIFACT_ROOT`.

- [ ] **Step 4: Verify a failing command propagates its status**

```bash
ARTIFACT_ROOT="$(mktemp -d)" scripts/agent/platforms/local.sh \
  pr-fail highline-runner:test 'exit 4'
echo "exit=$?"
```

Expected: `exit=4`.

- [ ] **Step 5: Commit**

```bash
git add scripts/agent/platforms/local.sh
git commit -m "feat(platforms): add local docker runner"
```

---

### Task 5: OVH platform script

**Files:**
- Create: `scripts/agent/platforms/ovh.sh`

**Interfaces:**
- Consumes: the exact `ovhai` flags and JSON field paths recorded in Task 1; the entrypoint contract from Task 2.
- Produces: `platforms/ovh.sh <run-id> <image> <command> [artifact-path...]`, submitting a job, polling to a terminal state, and exiting 0 only if the job finished cleanly.

- [ ] **Step 1: Write the script**

Create `scripts/agent/platforms/ovh.sh`. Correct the flag spellings and the two `jq` paths against what Task 1 recorded if they differ:

```bash
#!/usr/bin/env bash
# Schedule a runner job on OVHcloud AI Training and wait for it to finish.
#
# usage: ovh.sh <run-id> <image> <command> [artifact-path...]
#
# Environment:
#   OVH_CPU      CPUs to request (default: 8, max 12)
#   OVH_BUCKET   Object Storage bucket attached at /artifacts
#   OVH_REGION   region of that bucket; must match the job's region
#   POLL_SECONDS seconds between status checks (default: 30)
set -euo pipefail

OVH_CPU="${OVH_CPU:-8}"
OVH_BUCKET="${OVH_BUCKET:-highline-runs}"
OVH_REGION="${OVH_REGION:-GRA}"
POLL_SECONDS="${POLL_SECONDS:-30}"

if [ "$#" -lt 3 ]; then
    echo "usage: ovh.sh <run-id> <image> <command> [artifact-path...]" >&2
    exit 2
fi

RUN_ID="$1"
IMAGE="$2"
COMMAND="$3"
shift 3

ARTIFACTS=""
if [ "$#" -gt 0 ]; then
    ARTIFACTS="$(printf '%s\n' "$@")"
fi

JOB_ID="$(
    ovhai job run \
        --name "run-$RUN_ID" \
        --cpu "$OVH_CPU" \
        --volume "$OVH_BUCKET@$OVH_REGION:/artifacts:rw" \
        --env "RUN_ID=$RUN_ID" \
        --env "ARTIFACTS=$ARTIFACTS" \
        --env "ARTIFACT_DIR=/artifacts" \
        --output json \
        "$IMAGE" -- "$COMMAND" | jq -r '.id'
)"
echo "submitted job $JOB_ID for $RUN_ID" >&2

while true; do
    STATE="$(ovhai job get "$JOB_ID" --output json | jq -r '.status.state')"
    case "$STATE" in
    DONE)
        echo "job $JOB_ID finished: $STATE" >&2
        exit 0
        ;;
    FAILED | ERROR | TIMEOUT | INTERRUPTED)
        echo "job $JOB_ID finished: $STATE" >&2
        echo "logs: ovhai job logs $JOB_ID" >&2
        exit 1
        ;;
    esac
    sleep "$POLL_SECONDS"
done
```

- [ ] **Step 2: Verify argument handling**

```bash
bash -n scripts/agent/platforms/ovh.sh
chmod +x scripts/agent/platforms/ovh.sh
scripts/agent/platforms/ovh.sh pr-7 img:tag; echo "exit=$?"
```

Expected: usage message, `exit=2`.

- [ ] **Step 3: Smoke-run a cheap job on real OVH**

```bash
OVH_CPU=1 OVH_BUCKET=<bucket> OVH_REGION=<region> \
  scripts/agent/platforms/ovh.sh \
  smoke-1 "ghcr.io/agsti/highline_scout/runner:sha-$(git rev-parse --short HEAD)" \
  'mkdir -p out && just --version > out/just.txt' out
echo "exit=$?"
```

Expected: `exit=0` within a few minutes; `runs/smoke-1/out/just.txt` and `run.log` appear in the bucket. If it fails, read `ovhai job logs <job-id>` — a pull failure means the package is still private (Task 3 Step 5).

- [ ] **Step 4: Verify a failing job exits non-zero**

```bash
OVH_CPU=1 OVH_BUCKET=<bucket> OVH_REGION=<region> \
  scripts/agent/platforms/ovh.sh \
  smoke-fail "ghcr.io/agsti/highline_scout/runner:sha-$(git rev-parse --short HEAD)" \
  'exit 4'
echo "exit=$?"
```

Expected: `exit=1` (the script maps any bad terminal state to 1), with the state printed.

- [ ] **Step 5: Commit**

```bash
git add scripts/agent/platforms/ovh.sh
git commit -m "feat(platforms): add OVH AI Training runner"
```

---

### Task 6: Local orchestrator

**Files:**
- Create: `scripts/agent/run_pr.sh`

**Interfaces:**
- Consumes: `scripts/agent/agent_call.sh <agent>` (existing, prompt on stdin); the platform contract from Tasks 4 and 5.
- Produces: `run_pr.sh <claude|codex|pi> <pr-number> <local|ovh>`, with `DRY_RUN=1` printing the prompt instead of invoking the agent.

- [ ] **Step 1: Write the script**

Create `scripts/agent/run_pr.sh`:

```bash
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
```

- [ ] **Step 2: Verify argument handling**

```bash
bash -n scripts/agent/run_pr.sh
chmod +x scripts/agent/run_pr.sh
scripts/agent/run_pr.sh pi; echo "exit=$?"
scripts/agent/run_pr.sh pi 42 bogus; echo "exit=$?"
```

Expected: usage message then `exit=2`; then an "unknown platform 'bogus'" message and `exit=2`. The platform check must come before any `gh` call so this second case costs no network round-trip.

- [ ] **Step 3: Inspect the generated prompt against a real PR**

```bash
DRY_RUN=1 scripts/agent/run_pr.sh pi <open-pr-number> ovh
```

Expected: a prompt naming that PR, `platforms/ovh.sh`, `pr-<N>` as the run id, and a `sha-`-pinned image whose tag matches that PR's head SHA.

- [ ] **Step 4: Commit**

```bash
git add scripts/agent/run_pr.sh
git commit -m "feat(agent): add PR-run orchestrator"
```

---

### Task 7: Require an artifacts section in generated PRs

**Files:**
- Modify: `scripts/agent/develop_issue.sh` (the heredoc prompt, near the "how to run" instruction)

**Interfaces:**
- Consumes: nothing.
- Produces: PR bodies carrying an "artifacts" section, which Task 6's orchestrator requires.

- [ ] **Step 1: Read the current prompt**

```bash
cat scripts/agent/develop_issue.sh
```

Locate the numbered instruction that asks for the "how to run" section.

- [ ] **Step 2: Add the artifacts instruction**

Immediately after the "how to run" instruction, insert a new numbered item:

```
9. In the PR, add a section "artifacts" listing the repo-relative paths whose
   outputs are worth keeping after the run (e.g. data/italy/). One path per
   line. If the change produces no durable output, write "none".
```

Renumber the following instruction so the list stays sequential.

- [ ] **Step 3: Verify**

```bash
bash -n scripts/agent/develop_issue.sh
grep -n "how to run\|artifacts" scripts/agent/develop_issue.sh
```

Expected: no syntax errors; both sections appear in the prompt, in order.

- [ ] **Step 4: Commit**

```bash
git add scripts/agent/develop_issue.sh
git commit -m "feat(agent): require an artifacts section in generated PRs"
```

---

## Verification

End to end, once all tasks are done:

1. Open a PR with a how-to-run and an artifacts section.
2. Wait for CI to publish `ghcr.io/agsti/highline_scout/runner:sha-<short>` for its head commit.
3. `DRY_RUN=1 scripts/agent/run_pr.sh pi <pr> ovh` — confirm the prompt pins the right image.
4. `scripts/agent/run_pr.sh pi <pr> ovh` — confirm a verdict comment lands on the PR and the declared artifacts appear under `runs/pr-<N>/` in the bucket.
