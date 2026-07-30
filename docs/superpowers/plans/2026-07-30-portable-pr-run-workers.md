# Portable PR-run workers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a PR's "how to run" commands on disposable cloud capacity from a CI-built image, keep the declared outputs, and report the verdict back to the PR.

**Architecture:** Three layers. CI builds a `runner` image per commit whose entrypoint runs one command and copies declared paths to an artifact mount. Thin per-platform scripts (`local.sh`, `ovh.sh`) schedule that image and share one calling convention. A local orchestrator agent resolves a PR to its image tag, reads the how-to-run and artifacts sections from the PR body, invokes a platform script, and comments the result.

**Tech Stack:** Bash, Docker/Buildx, GitHub Actions, GHCR, OVHcloud AI Training (`ovhai`), `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-07-30-portable-pr-run-workers-design.md`

## Global Constraints

- All scripts are `bash` with `set -euo pipefail` (test-only scripts use `set -uo pipefail`, matching `tests/scripts/test_create_hetzner_servers.sh`).
- Scripts that are unit-tested must guard their entry point so the file can be sourced without executing: `if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then main "$@"; fi`.
- Shell tests live in `tests/scripts/test_<script-name>.sh`, source the script under test, use the existing `assert_eq` / `assert_contains` helper style, print `All tests passed.` and exit non-zero on failure. Run them with `bash tests/scripts/<file>.sh`.
- Image reference: `ghcr.io/agsti/highline_scout/runner`, pinned by the immutable `sha-<short>` tag. Never the branch tag.
- Entrypoint contract: positional `<command>`; environment `RUN_ID`, `ARTIFACTS` (newline-separated repo-relative paths), `ARTIFACT_DIR` (default `/artifacts`).
- Platform script contract: `<run-id> <image> <command> [artifact-path...]`, synchronous, exits with the job's status.
- The runner image contains no agent CLI, no LLM API key, no `gh`, and no GitHub token.
- This machine is memory-tight: run any `pytest` under `ulimit -v` and `timeout`, using `.venv/bin/python` rather than `uv run`.

---

## File Structure

| File | Responsibility |
|---|---|
| `docs/superpowers/notes/2026-07-30-ovh-ai-training-probe.md` | Measured OVH facts (UID, disk, CLI syntax) that later tasks depend on |
| `scripts/runner/entrypoint.sh` | Run one command, collect declared artifacts + log. Lives in the image |
| `tests/scripts/test_runner_entrypoint.sh` | Unit tests for artifact collection and exit-status propagation |
| `Dockerfile` | Adds a `runner` stage on top of the existing builder |
| `.github/workflows/ci.yml` | Adds a build-push step for the `runner` target |
| `scripts/agent/platforms/local.sh` | Schedule a job via `docker run` |
| `tests/scripts/test_platforms_local.sh` | Unit tests with a stubbed `docker` |
| `scripts/agent/platforms/ovh.sh` | Schedule a job via `ovhai job run`, poll to completion |
| `tests/scripts/test_platforms_ovh.sh` | Unit tests with a stubbed `ovhai` |
| `scripts/agent/run_pr.sh` | Local orchestrator: PR → image + sections → platform script → PR comment |
| `tests/scripts/test_run_pr.sh` | Unit tests for prompt construction and arg validation |
| `scripts/agent/develop_issue.sh` | Gains the artifacts-section instruction in its prompt |

---

### Task 1: Probe OVH AI Training and record the facts

The spec lists three unverified facts that decide the Dockerfile's user, where `data/` can live, and the exact `ovhai` syntax Task 6 hardcodes. Settle them with a throwaway job before writing code against guesses.

**Files:**
- Create: `docs/superpowers/notes/2026-07-30-ovh-ai-training-probe.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the measured values Tasks 3 and 6 read — container UID, writable paths, local disk GB at a given `--cpu`, the exact `ovhai job run` flag spelling, the JSON field holding a job's id and terminal state.

- [ ] **Step 1: Install and authenticate the CLI**

```bash
curl -s https://cli.bhs.ai.cloud.ovh.net/install.sh | bash
ovhai login
ovhai me
```

Expected: `ovhai me` prints your user without error. If login is interactive, run it yourself in the terminal with `! ovhai login`.

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

Record the JSON path to the job id and to its terminal state, plus the exact set of terminal state strings observed (e.g. `DONE`, `FAILED`). Task 6 parses these.

- [ ] **Step 6: Confirm billing source**

Check the OVHcloud control panel that the probe jobs were billed against trial credits rather than a payment method. Record yes/no. If no, stop and raise it — the whole approach assumes credits cover AI Training.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/notes/2026-07-30-ovh-ai-training-probe.md
git commit -m "docs: record measured OVH AI Training job facts"
```

---

### Task 2: Runner entrypoint script

**Files:**
- Create: `scripts/runner/entrypoint.sh`
- Test: `tests/scripts/test_runner_entrypoint.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: `collect_artifacts <dest-dir> <newline-separated-paths>` and `main <command>`, sourced by the test. Writes to `$ARTIFACT_DIR/runs/$RUN_ID/`, containing `run.log` plus each declared path at its original relative position.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_runner_entrypoint.sh`:

```bash
#!/usr/bin/env bash
# Tests for scripts/runner/entrypoint.sh.
# Run directly: bash tests/scripts/test_runner_entrypoint.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO_ROOT/scripts/runner/entrypoint.sh"

FAILURES=0

assert_eq() {
    local expected="$1" actual="$2" msg="$3"
    if [[ "$expected" != "$actual" ]]; then
        echo "FAIL: $msg" >&2
        echo "  expected: $expected" >&2
        echo "  actual:   $actual" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

assert_contains() {
    local haystack="$1" needle="$2" msg="$3"
    if [[ "$haystack" != *"$needle"* ]]; then
        echo "FAIL: $msg" >&2
        echo "  expected to contain: $needle" >&2
        echo "  actual: $haystack" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

test_collect_artifacts_preserves_relative_paths() {
    local src dest
    src="$(mktemp -d)"; dest="$(mktemp -d)"
    mkdir -p "$src/data/italy"
    printf 'rows' > "$src/data/italy/pairs.parquet"
    (cd "$src" && collect_artifacts "$dest" "data/italy") >/dev/null 2>&1
    assert_eq "rows" "$(cat "$dest/data/italy/pairs.parquet" 2>/dev/null)" \
        "declared path copied at its original relative position"
    rm -rf "$src" "$dest"
}

test_collect_artifacts_handles_multiple_paths() {
    local src dest
    src="$(mktemp -d)"; dest="$(mktemp -d)"
    mkdir -p "$src/data" "$src/logs"
    printf 'a' > "$src/data/a.txt"
    printf 'b' > "$src/logs/b.txt"
    (cd "$src" && collect_artifacts "$dest" "$(printf 'data\nlogs')") >/dev/null 2>&1
    assert_eq "a" "$(cat "$dest/data/a.txt" 2>/dev/null)" "first path copied"
    assert_eq "b" "$(cat "$dest/logs/b.txt" 2>/dev/null)" "second path copied"
    rm -rf "$src" "$dest"
}

test_collect_artifacts_warns_on_missing_path_without_failing() {
    local src dest out status
    src="$(mktemp -d)"; dest="$(mktemp -d)"
    out="$( (cd "$src" && collect_artifacts "$dest" "data/nope") 2>&1 )"
    status=$?
    assert_eq "0" "$status" "a missing declared path must not abort collection"
    assert_contains "$out" "data/nope" "missing path is named in the warning"
    rm -rf "$src" "$dest"
}

test_collect_artifacts_ignores_blank_lines() {
    local src dest out
    src="$(mktemp -d)"; dest="$(mktemp -d)"
    out="$( (cd "$src" && collect_artifacts "$dest" "$(printf '\n\n')") 2>&1 )"
    assert_eq "" "$out" "blank artifact lines produce no warnings"
    rm -rf "$src" "$dest"
}

test_collect_artifacts_preserves_relative_paths
test_collect_artifacts_handles_multiple_paths
test_collect_artifacts_warns_on_missing_path_without_failing
test_collect_artifacts_ignores_blank_lines

if [[ $FAILURES -gt 0 ]]; then
    echo "$FAILURES test(s) failed" >&2
    exit 1
fi
echo "All tests passed."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/scripts/test_runner_entrypoint.sh`
Expected: FAIL — `No such file or directory` for `scripts/runner/entrypoint.sh`.

- [ ] **Step 3: Write minimal implementation**

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
DEST=""

collect_artifacts() {
    local dest="$1" paths="$2" path parent
    mkdir -p "$dest"
    while IFS= read -r path; do
        [ -z "$path" ] && continue
        if [ ! -e "$path" ]; then
            echo "runner: declared artifact '$path' does not exist, skipping" >&2
            continue
        fi
        parent="$(dirname "$path")"
        mkdir -p "$dest/$parent"
        cp -r "$path" "$dest/$parent/"
    done <<< "$paths"
    return 0
}

main() {
    if [ "$#" -lt 1 ]; then
        echo "usage: entrypoint.sh <command>" >&2
        exit 2
    fi
    DEST="$ARTIFACT_DIR/runs/$RUN_ID"
    mkdir -p "$DEST"
    trap 'collect_artifacts "$DEST" "$ARTIFACTS"' EXIT
    bash -lc "$*" 2>&1 | tee "$DEST/run.log"
    exit "${PIPESTATUS[0]}"
}

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
    main "$@"
fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/scripts/test_runner_entrypoint.sh`
Expected: `All tests passed.`

- [ ] **Step 5: Verify the exit-status and trap behaviour end to end**

```bash
chmod +x scripts/runner/entrypoint.sh
d="$(mktemp -d)"
RUN_ID=t1 ARTIFACT_DIR="$d" ARTIFACTS="out" scripts/runner/entrypoint.sh 'mkdir -p out && echo hi > out/f && exit 3'
echo "exit=$?"
ls "$d/runs/t1" "$d/runs/t1/out"
cat "$d/runs/t1/run.log"
```

Expected: `exit=3`; `run.log` contains nothing from stdout of `mkdir`, but exists; `out/f` was still collected despite the non-zero exit.

- [ ] **Step 6: Commit**

```bash
git add scripts/runner/entrypoint.sh tests/scripts/test_runner_entrypoint.sh
git commit -m "feat(runner): add job entrypoint that keeps declared artifacts"
```

---

### Task 3: Runner stage in the Dockerfile

**Files:**
- Modify: `Dockerfile` (append a new stage after the existing final stage)

**Interfaces:**
- Consumes: `scripts/runner/entrypoint.sh` from Task 2; the UID finding from Task 1.
- Produces: build target `runner`, whose entrypoint is `/app/entrypoint.sh` and whose working directory is `/app` with the `highliner` package and its venv on `PATH`.

- [ ] **Step 1: Read the existing Dockerfile**

Run: `cat Dockerfile`
Note the builder stage name, the venv path (`/app/.venv`), the `app` user creation, and the final `PATH` setting — the runner stage mirrors them.

- [ ] **Step 2: Append the runner stage**

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

If Task 1 found that AI Training forces a specific UID, leave the stage running as root (no `USER` line) so the entrypoint can write regardless — and note that decision in the probe notes file.

- [ ] **Step 3: Build the runner target**

Run: `docker build --target runner -t highline-runner:test .`
Expected: build succeeds.

- [ ] **Step 4: Verify the image runs a command and keeps artifacts**

```bash
d="$(mktemp -d)"
docker run --rm \
  -e RUN_ID=t2 -e ARTIFACTS='out' -e ARTIFACT_DIR=/artifacts \
  -v "$d:/artifacts" \
  highline-runner:test 'mkdir -p out && just --version > out/just.txt'
cat "$d/runs/t2/out/just.txt"
```

Expected: prints a `just` version, proving `just` is installed and artifacts survive the container.

- [ ] **Step 5: Verify the server image still builds**

Run: `docker build -t highline-server:test .`
Expected: succeeds and still selects the server stage as default — the runner stage must not become the implicit final stage. If it did, move the runner stage above the server stage.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile
git commit -m "feat(docker): add runner stage with just and unar"
```

---

### Task 4: Publish the runner image from CI

**Files:**
- Modify: `.github/workflows/ci.yml:148-189` (the `docker` job)

**Interfaces:**
- Consumes: the `runner` build target from Task 3.
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

- [ ] **Step 2: Commit and push the branch**

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
```

Expected: includes a `sha-<short>` tag matching `git rev-parse --short HEAD`.

- [ ] **Step 5: Make the package public**

In the GitHub UI, set the `highline_scout/runner` package visibility to public so OVH pulls need no credentials. Verify anonymously:

```bash
docker logout ghcr.io
docker pull ghcr.io/agsti/highline_scout/runner:sha-<short>
```

Expected: pull succeeds without login.

---

### Task 5: Local platform script

**Files:**
- Create: `scripts/agent/platforms/local.sh`
- Test: `tests/scripts/test_platforms_local.sh`

**Interfaces:**
- Consumes: the entrypoint contract from Task 2.
- Produces: `main <run-id> <image> <command> [artifact-path...]`, and `docker_args <run-id> <image> <command> <newline-separated-artifacts>` which prints the argument list passed to `docker`, so tests can assert on it without running Docker.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_platforms_local.sh`:

```bash
#!/usr/bin/env bash
# Tests for scripts/agent/platforms/local.sh.
# Run directly: bash tests/scripts/test_platforms_local.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO_ROOT/scripts/agent/platforms/local.sh"
# The sourced script sets -e; turn it back off so tests can exercise failure
# paths without aborting this shell.
set +e

FAILURES=0

assert_eq() {
    local expected="$1" actual="$2" msg="$3"
    if [[ "$expected" != "$actual" ]]; then
        echo "FAIL: $msg" >&2
        echo "  expected: $expected" >&2
        echo "  actual:   $actual" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

assert_contains() {
    local haystack="$1" needle="$2" msg="$3"
    if [[ "$haystack" != *"$needle"* ]]; then
        echo "FAIL: $msg" >&2
        echo "  expected to contain: $needle" >&2
        echo "  actual: $haystack" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

test_docker_args_passes_contract_env() {
    local out
    out="$(ARTIFACT_ROOT=/tmp/runs docker_args pr-7 img:tag 'just test' 'data/italy')"
    assert_contains "$out" "RUN_ID=pr-7" "run id passed as RUN_ID"
    assert_contains "$out" "ARTIFACTS=data/italy" "artifacts passed as ARTIFACTS"
    assert_contains "$out" "ARTIFACT_DIR=/artifacts" "artifact dir fixed inside the container"
    assert_contains "$out" "/tmp/runs:/artifacts" "artifact root bind-mounted"
    assert_contains "$out" "img:tag" "image included"
    assert_contains "$out" "just test" "command included"
}

test_docker_args_joins_multiple_artifacts_with_newlines() {
    local out
    out="$(ARTIFACT_ROOT=/tmp/runs docker_args pr-7 img:tag 'just test' "$(printf 'data/italy\ndata/spain')")"
    assert_contains "$out" "data/italy" "first artifact present"
    assert_contains "$out" "data/spain" "second artifact present"
}

test_main_rejects_too_few_args() {
    local out status
    out="$(main pr-7 img:tag 2>&1)"; status=$?
    assert_eq "2" "$status" "missing command exits 2"
    assert_contains "$out" "usage:" "usage printed"
}

test_docker_args_passes_contract_env
test_docker_args_joins_multiple_artifacts_with_newlines
test_main_rejects_too_few_args

if [[ $FAILURES -gt 0 ]]; then
    echo "$FAILURES test(s) failed" >&2
    exit 1
fi
echo "All tests passed."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/scripts/test_platforms_local.sh`
Expected: FAIL — `No such file or directory`.

- [ ] **Step 3: Write minimal implementation**

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

docker_args() {
    local run_id="$1" image="$2" command="$3" artifacts="$4"
    printf '%s\n' \
        run --rm \
        -e "RUN_ID=$run_id" \
        -e "ARTIFACTS=$artifacts" \
        -e "ARTIFACT_DIR=/artifacts" \
        -v "$ARTIFACT_ROOT:/artifacts" \
        "$image" "$command"
}

main() {
    if [ "$#" -lt 3 ]; then
        echo "usage: local.sh <run-id> <image> <command> [artifact-path...]" >&2
        return 2
    fi
    local run_id="$1" image="$2" command="$3"
    shift 3
    local artifacts=""
    if [ "$#" -gt 0 ]; then
        artifacts="$(printf '%s\n' "$@")"
    fi
    mkdir -p "$ARTIFACT_ROOT"
    local args=()
    while IFS= read -r line; do args+=("$line"); done < <(
        docker_args "$run_id" "$image" "$command" "$artifacts"
    )
    docker "${args[@]}"
}

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
    main "$@"
fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/scripts/test_platforms_local.sh`
Expected: `All tests passed.`

- [ ] **Step 5: Verify against the real image**

```bash
chmod +x scripts/agent/platforms/local.sh
ARTIFACT_ROOT="$(mktemp -d)" scripts/agent/platforms/local.sh \
  pr-test highline-runner:test 'mkdir -p out && echo ok > out/f' out
```

Expected: exit 0, and `runs/pr-test/out/f` exists under the temp `ARTIFACT_ROOT`.

- [ ] **Step 6: Commit**

```bash
git add scripts/agent/platforms/local.sh tests/scripts/test_platforms_local.sh
git commit -m "feat(platforms): add local docker runner"
```

---

### Task 6: OVH platform script

**Files:**
- Create: `scripts/agent/platforms/ovh.sh`
- Test: `tests/scripts/test_platforms_ovh.sh`

**Interfaces:**
- Consumes: the exact `ovhai` flags and JSON field paths recorded in Task 1; the entrypoint contract from Task 2.
- Produces: `ovhai_args <run-id> <image> <command> <newline-separated-artifacts>` printing the submit argument list, `terminal_status <state>` mapping a state string to 0/1/2 (success/failure/still-running), and `main` with the shared platform signature.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_platforms_ovh.sh`:

```bash
#!/usr/bin/env bash
# Tests for scripts/agent/platforms/ovh.sh.
# Run directly: bash tests/scripts/test_platforms_ovh.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO_ROOT/scripts/agent/platforms/ovh.sh"
# The sourced script sets -e; turn it back off so tests can exercise failure
# paths without aborting this shell.
set +e

FAILURES=0

assert_eq() {
    local expected="$1" actual="$2" msg="$3"
    if [[ "$expected" != "$actual" ]]; then
        echo "FAIL: $msg" >&2
        echo "  expected: $expected" >&2
        echo "  actual:   $actual" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

assert_contains() {
    local haystack="$1" needle="$2" msg="$3"
    if [[ "$haystack" != *"$needle"* ]]; then
        echo "FAIL: $msg" >&2
        echo "  expected to contain: $needle" >&2
        echo "  actual: $haystack" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

test_ovhai_args_include_cpu_volume_and_env() {
    local out
    out="$(OVH_CPU=8 OVH_BUCKET=highline-runs OVH_REGION=GRA \
        ovhai_args pr-7 img:tag 'just etl-chunk italy 8' 'data/italy')"
    assert_contains "$out" "--cpu" "cpu flag present"
    assert_contains "$out" "8" "cpu count present"
    assert_contains "$out" "highline-runs@GRA:/artifacts:rw" "bucket attached read-write"
    assert_contains "$out" "RUN_ID=pr-7" "run id passed"
    assert_contains "$out" "ARTIFACTS=data/italy" "artifacts passed"
    assert_contains "$out" "img:tag" "image present"
}

test_terminal_status_maps_states() {
    terminal_status DONE; assert_eq "0" "$?" "DONE is success"
    terminal_status FAILED; assert_eq "1" "$?" "FAILED is failure"
    terminal_status ERROR; assert_eq "1" "$?" "ERROR is failure"
    terminal_status TIMEOUT; assert_eq "1" "$?" "TIMEOUT is failure"
    terminal_status RUNNING; assert_eq "2" "$?" "RUNNING is not terminal"
    terminal_status PENDING; assert_eq "2" "$?" "PENDING is not terminal"
}

test_main_rejects_too_few_args() {
    local out status
    out="$(main pr-7 img:tag 2>&1)"; status=$?
    assert_eq "2" "$status" "missing command exits 2"
    assert_contains "$out" "usage:" "usage printed"
}

test_ovhai_args_include_cpu_volume_and_env
test_terminal_status_maps_states
test_main_rejects_too_few_args

if [[ $FAILURES -gt 0 ]]; then
    echo "$FAILURES test(s) failed" >&2
    exit 1
fi
echo "All tests passed."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/scripts/test_platforms_ovh.sh`
Expected: FAIL — `No such file or directory`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/agent/platforms/ovh.sh`. Correct the flag spellings and the two `jq` paths against what Task 1 recorded if they differ from the values below:

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

ovhai_args() {
    local run_id="$1" image="$2" command="$3" artifacts="$4"
    printf '%s\n' \
        job run \
        --name "run-$run_id" \
        --cpu "$OVH_CPU" \
        --volume "$OVH_BUCKET@$OVH_REGION:/artifacts:rw" \
        --env "RUN_ID=$run_id" \
        --env "ARTIFACTS=$artifacts" \
        --env "ARTIFACT_DIR=/artifacts" \
        --output json \
        "$image" -- "$command"
}

# 0 = finished ok, 1 = finished badly, 2 = not terminal yet
terminal_status() {
    case "$1" in
    DONE) return 0 ;;
    FAILED | ERROR | TIMEOUT | INTERRUPTED) return 1 ;;
    *) return 2 ;;
    esac
}

wait_for_job() {
    local job_id="$1" state status
    while true; do
        state="$(ovhai job get "$job_id" --output json | jq -r '.status.state')"
        terminal_status "$state"
        status=$?
        if [ "$status" -ne 2 ]; then
            echo "job $job_id finished: $state" >&2
            return "$status"
        fi
        sleep "$POLL_SECONDS"
    done
}

main() {
    if [ "$#" -lt 3 ]; then
        echo "usage: ovh.sh <run-id> <image> <command> [artifact-path...]" >&2
        return 2
    fi
    local run_id="$1" image="$2" command="$3"
    shift 3
    local artifacts=""
    if [ "$#" -gt 0 ]; then
        artifacts="$(printf '%s\n' "$@")"
    fi

    local args=()
    while IFS= read -r line; do args+=("$line"); done < <(
        ovhai_args "$run_id" "$image" "$command" "$artifacts"
    )

    local job_id
    job_id="$(ovhai "${args[@]}" | jq -r '.id')"
    echo "submitted job $job_id for $run_id" >&2

    wait_for_job "$job_id"
}

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
    main "$@"
fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/scripts/test_platforms_ovh.sh`
Expected: `All tests passed.`

- [ ] **Step 5: Verify against real OVH with a cheap command**

```bash
chmod +x scripts/agent/platforms/ovh.sh
OVH_CPU=1 scripts/agent/platforms/ovh.sh \
  smoke-1 ghcr.io/agsti/highline_scout/runner:sha-<short> \
  'mkdir -p out && just --version > out/just.txt' out
```

Expected: exits 0 within a few minutes, and `runs/smoke-1/out/just.txt` plus `run.log` appear in the bucket. Confirm with `ovhai job logs <job-id>` if it fails.

- [ ] **Step 6: Commit**

```bash
git add scripts/agent/platforms/ovh.sh tests/scripts/test_platforms_ovh.sh
git commit -m "feat(platforms): add OVH AI Training runner"
```

---

### Task 7: Local orchestrator

**Files:**
- Create: `scripts/agent/run_pr.sh`
- Test: `tests/scripts/test_run_pr.sh`

**Interfaces:**
- Consumes: `scripts/agent/agent_call.sh <agent>` (existing, prompt on stdin); the platform script signature from Tasks 5 and 6.
- Produces: `build_prompt <pr-number> <platform> <image>` printing the orchestrator prompt, and `image_ref <pr-number>` printing `ghcr.io/agsti/highline_scout/runner:sha-<short-head-sha>`.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_run_pr.sh`:

```bash
#!/usr/bin/env bash
# Tests for scripts/agent/run_pr.sh.
# Run directly: bash tests/scripts/test_run_pr.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO_ROOT/scripts/agent/run_pr.sh"
# The sourced script sets -e; turn it back off so tests can exercise failure
# paths without aborting this shell.
set +e

FAILURES=0

assert_eq() {
    local expected="$1" actual="$2" msg="$3"
    if [[ "$expected" != "$actual" ]]; then
        echo "FAIL: $msg" >&2
        echo "  expected: $expected" >&2
        echo "  actual:   $actual" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

assert_contains() {
    local haystack="$1" needle="$2" msg="$3"
    if [[ "$haystack" != *"$needle"* ]]; then
        echo "FAIL: $msg" >&2
        echo "  expected to contain: $needle" >&2
        echo "  actual: $haystack" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

test_build_prompt_names_platform_script_and_image() {
    local out
    out="$(build_prompt 42 ovh ghcr.io/agsti/highline_scout/runner:sha-abc1234)"
    assert_contains "$out" "#42" "PR number stated"
    assert_contains "$out" "scripts/agent/platforms/ovh.sh" "platform script named"
    assert_contains "$out" "sha-abc1234" "pinned image passed through"
    assert_contains "$out" "how to run" "prompt asks for the how-to-run section"
    assert_contains "$out" "artifacts" "prompt asks for the artifacts section"
}

test_build_prompt_switches_platform_script() {
    local out
    out="$(build_prompt 42 local img:tag)"
    assert_contains "$out" "scripts/agent/platforms/local.sh" "local platform script named"
}

test_main_rejects_unknown_platform() {
    local out status
    out="$(main pi 42 bogus 2>&1)"; status=$?
    assert_eq "2" "$status" "unknown platform exits 2"
    assert_contains "$out" "bogus" "offending platform named"
}

test_main_rejects_too_few_args() {
    local out status
    out="$(main pi 2>&1)"; status=$?
    assert_eq "2" "$status" "missing platform exits 2"
    assert_contains "$out" "usage:" "usage printed"
}

test_build_prompt_names_platform_script_and_image
test_build_prompt_switches_platform_script
test_main_rejects_unknown_platform
test_main_rejects_too_few_args

if [[ $FAILURES -gt 0 ]]; then
    echo "$FAILURES test(s) failed" >&2
    exit 1
fi
echo "All tests passed."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash tests/scripts/test_run_pr.sh`
Expected: FAIL — `No such file or directory`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/agent/run_pr.sh`:

```bash
#!/usr/bin/env bash
# Run a PR's "how to run" section on a platform and report back on the PR.
#
# usage: run_pr.sh <claude|codex|pi> <pr-number> <local|ovh>
set -euo pipefail

GH_REPO="${GH_REPO:-}"
SCRIPT_DIR="$(dirname "$0")"
IMAGE_REPO="${IMAGE_REPO:-ghcr.io/agsti/highline_scout/runner}"

# Resolved lazily, not at source time, so tests can source this file without
# needing gh or a network round-trip.
resolve_repo() {
    [ -n "$GH_REPO" ] ||
        GH_REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
    export GH_REPO
}

image_ref() {
    local pr="$1" sha
    sha="$(gh pr view "$pr" --repo "$GH_REPO" --json headRefOid --jq '.headRefOid')"
    printf '%s:sha-%s' "$IMAGE_REPO" "${sha:0:7}"
}

build_prompt() {
    local pr="$1" platform="$2" image="$3"
    cat <<EOF
You are running the verification job for GitHub pull request #${pr}.
Read AGENTS.md.

1. Read the PR body:
   gh pr view ${pr} --repo ${GH_REPO} --json title,body

2. Extract two things from it:
   - the "how to run" section: the exact commands, in order
   - the "artifacts" section: the repo-relative paths whose outputs must be kept
   If either section is missing, stop, comment on the PR saying which one is
   missing, and exit non-zero. Do not guess.

3. Schedule the job. The image is already built by CI; do not build anything:
   ${SCRIPT_DIR}/platforms/${platform}.sh pr-${pr} ${image} "<command>" <artifact-path...>
   Join multiple how-to-run commands into a single shell command with &&.
   The script is synchronous and exits with the job's status.

4. Report the outcome as a PR comment: pass or fail, how long it took, the
   artifact paths that were kept, and the tail of the log if it failed.
   gh pr comment ${pr} --repo ${GH_REPO} --body "..."

5. Exit with the job's status.
EOF
}

main() {
    if [ "$#" -lt 3 ]; then
        echo "usage: run_pr.sh <claude|codex|pi> <pr-number> <local|ovh>" >&2
        return 2
    fi
    local agent="$1" pr="$2" platform="$3"

    case "$platform" in
    local | ovh) ;;
    *)
        echo "run_pr.sh: unknown platform '${platform}' (expected local or ovh)" >&2
        return 2
        ;;
    esac

    resolve_repo
    local image
    image="$(image_ref "$pr")"
    build_prompt "$pr" "$platform" "$image" | "$SCRIPT_DIR/agent_call.sh" "$agent"
}

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
    main "$@"
fi
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash tests/scripts/test_run_pr.sh`
Expected: `All tests passed.`

Note: `test_main_rejects_unknown_platform` must reach the platform check before `image_ref` runs, so keep the `case` above the `image_ref` call.

- [ ] **Step 5: Dry-run the prompt against a real PR**

```bash
chmod +x scripts/agent/run_pr.sh
source scripts/agent/run_pr.sh
build_prompt 42 ovh "$(image_ref 42)"
```

Expected: a prompt naming PR #42, `platforms/ovh.sh`, and a `sha-` pinned image. Substitute any open PR number.

- [ ] **Step 6: Commit**

```bash
git add scripts/agent/run_pr.sh tests/scripts/test_run_pr.sh
git commit -m "feat(agent): add PR-run orchestrator"
```

---

### Task 8: Require an artifacts section in generated PRs

**Files:**
- Modify: `scripts/agent/develop_issue.sh` (the heredoc prompt, near the "how to run" instruction)

**Interfaces:**
- Consumes: nothing.
- Produces: PR bodies carrying an "artifacts" section, which Task 7's orchestrator requires.

- [ ] **Step 1: Read the current prompt**

Run: `cat scripts/agent/develop_issue.sh`
Locate the numbered instruction that asks for the "how to run" section.

- [ ] **Step 2: Add the artifacts instruction**

Immediately after the "how to run" instruction, insert:

```
9. In the PR, add a section "artifacts" listing the repo-relative paths whose
   outputs are worth keeping after the run (e.g. data/italy/). One path per
   line. If the change produces no durable output, write "none".
```

Renumber the following instruction so the list stays sequential.

- [ ] **Step 3: Verify the script still parses and the prompt contains both sections**

```bash
bash -n scripts/agent/develop_issue.sh
grep -n "how to run\|artifacts" scripts/agent/develop_issue.sh
```

Expected: no syntax errors; both sections appear in the prompt.

- [ ] **Step 4: Commit**

```bash
git add scripts/agent/develop_issue.sh
git commit -m "feat(agent): require an artifacts section in generated PRs"
```

---

## Verification

After all tasks, from the repo root:

```bash
for t in tests/scripts/test_runner_entrypoint.sh \
         tests/scripts/test_platforms_local.sh \
         tests/scripts/test_platforms_ovh.sh \
         tests/scripts/test_run_pr.sh; do
    echo "== $t"; bash "$t" || echo "FAILED: $t"
done
```

Expected: `All tests passed.` from each.

End-to-end: open a PR with a how-to-run and an artifacts section, wait for CI to publish the runner image, then `scripts/agent/run_pr.sh pi <pr> ovh` and confirm a verdict comment lands on the PR with artifacts in the bucket.
