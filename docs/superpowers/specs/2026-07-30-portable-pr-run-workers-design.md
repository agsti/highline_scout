# Portable PR-run workers

## Purpose

Run a PR's "how to run" section on disposable cloud capacity, keep the outputs,
and report the verdict back to the PR.

`scripts/agent/develop_issue.sh` produces PRs that carry a "how to run" section
listing the exact commands that exercise the change. For an ETL PR those
commands are a real `just etl-*` run: hours of CPU, tens of GB of DTM downloads,
and `data/<country>/…` parquet as the payload. This design covers the worker
that executes those commands somewhere other than the developer's machine.

The immediate target is OVHcloud AI Training, billed per minute against Public
Cloud trial credits, but nothing about the job is OVH-specific: the same run
works under plain `docker run` locally or on another provider by adding one
script.

## Architecture

Three layers. Intelligence lives only in the outermost one.

### 1. The job image (`ghcr.io/agsti/highline_scout/runner`)

The branch's code, already built. CI produces one image per pushed commit, so a
job is a pull and a run — no cloning, no checkout, no dependency install at run
time, and nothing in the job that needs `git` or a GitHub token.

A new stage in the existing `Dockerfile`, reusing the `uv` builder layer that
the server image already builds, plus what ETL recipes need on top of it:

- `just` — the `etl-*` entry points are recipes
- `unar` — Chile's DTM archives use a RAR compression method `py7zr` can't read

No agent CLIs, no LLM API keys, no knowledge of GitHub or pull requests. The
image serves a human running a command by hand exactly as well as it serves the
orchestrator.

Entrypoint contract:

    <command>

with `RUN_ID`, `ARTIFACTS` (newline-separated repo-relative paths) and
`ARTIFACT_DIR` (default `/artifacts`) supplied as environment variables. It runs
`<command>`, copies each `ARTIFACTS` path plus the full log to
`$ARTIFACT_DIR/runs/$RUN_ID/`, and exits with the command's status.

`RUN_ID` is an opaque label. The orchestrator happens to pass `pr-<N>`; the
image neither knows nor cares.

### Publishing

A second `build-push-action` step in the existing `docker` CI job, sharing its
GHA cache and its `needs: check` gate — no image exists for a branch whose lint,
types or tests fail, which also stops credits being spent on one. The package is
public, like the repo, so pulls need no registry credentials.

Jobs pin the immutable `sha-<short>` tag rather than the branch tag, which moves
whenever the branch is pushed. The orchestrator resolves a PR to its head SHA to
build the reference.

### 2. Platform scripts

One executable per target, all sharing an interface:

    scripts/agent/platforms/local.sh <run-id> <image> <command> [artifact-path...]
    scripts/agent/platforms/ovh.sh   <run-id> <image> <command> [artifact-path...]

`local.sh` is a `docker run` with a bind mount. `ovh.sh` is an `ovhai job run`
with an Object Storage volume attached, polling until the job reaches a terminal
state. Both are synchronous and exit with the job's status, so the orchestrator
treats every platform identically. Both are runnable by hand.

Adding a platform means adding one script.

### 3. Local orchestrator

An agent on the developer's machine. Per PR it:

1. resolves the PR to its head SHA — hence its image tag — and reads the
   how-to-run and artifacts sections from the PR body, waiting for CI to publish
   the image if it is not there yet
2. invokes the platform script for wherever the job should run
3. reads the resulting log
4. posts the verdict as a PR comment

It is the only component that talks to an LLM, holds a GitHub token, or knows
what a PR is.

## The PR body is the contract

The orchestrator carries no per-country knowledge. Everything comes from the PR
body:

- a **how to run** section — the exact commands, in order, that exercise the
  change. `develop_issue.sh` already instructs the implementing agent to write
  this.
- an **artifacts** section — the paths whose contents must survive the run
  (e.g. `data/italy/`). This does not exist yet; `develop_issue.sh` gains one
  more numbered instruction requiring it.

A PR missing either section fails with that as the reported reason, rather than
the orchestrator guessing.

## Artifacts

Outputs land in `$ARTIFACT_DIR/runs/<run-id>/`: a bind mount locally, the
attached Object Storage bucket on OVH. Attaching the bucket the job already
writes to removes any separate upload step. The existing `s3://highlinescout`
bucket remains an option for the local runner, which has no volume to attach.

The log is written from an `EXIT` trap, not from the success path, so a run that
dies mid-ETL still leaves something to read.

## Teardown

There is none to build. AI Training bills per minute only while a job is
`RUNNING` and stops the moment it exits, so a finished job costs nothing and
leaves nothing to reap. Jobs auto-stop after seven consecutive days, which puts
a floor under a hung run.

This is the reason to prefer AI Training over provisioning Public Cloud
instances directly: a stopped instance keeps billing until deleted, which would
have required a self-delete step, a watchdog timer, and a reaper on the
developer's machine — three mechanisms guarding the one action that costs money
when it fails to fire.

## Secrets

The image holds none. Platform credentials (`ovhai` session, Object Storage
keys) belong to the platform script on the developer's machine; the GitHub token
belongs to the orchestrator. A job that leaks its whole environment leaks
nothing that matters.

## Sizing

Disk is the binding constraint, not CPU. A country ETL downloads 20+ GB of DTM
before writing any parquet. AI Training's local storage is ephemeral, scales
with the requested CPU count, and is documented as "limited and not the
recommended way to handle data"; the intended pattern is to attach an Object
Storage bucket and work against that. The bucket must be in the same region as
the job.

Jobs cap at 12 CPU, which covers the `just etl-chunk <country> 8` worker counts
in use. Memory needs headroom beyond the nominal ask: Italy's chunk ETL has
OOM'd before.

## Unverified before first build

Three facts that shape the Dockerfile and the storage layout, to be settled with
a throwaway hello-world job rather than assumed:

1. Actual local ephemeral disk per CPU. If well under ~100 GB, `data/` and
   `cache/` must live on the attached volume, whose throughput for tile-heavy
   work is then worth measuring.
2. Which user the container runs as. AI Training may impose a fixed non-root
   UID, which would conflict with the `app` (uid 1000) user the existing
   `Dockerfile` sets, and determines what must be writable for the artifact
   copy to succeed.
3. Whether Public Cloud trial credits apply to AI Training, or only to
   instances.

## Out of scope

- Autoscaling or a job queue. The orchestrator submits one job per PR and that
  is the whole scheduler.
- Reusing warm DTM caches between runs. Every job starts clean; caching terrain
  across runs is a later optimisation, and `cache/` is safe to lose.
- Changes to `develop_issue.sh` beyond adding the artifacts-section instruction
  to its prompt.
