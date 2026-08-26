---
name: running-prs-on-ovh
description: Use when running a PR's ETL or verification commands on OVHcloud AI Training rather than locally — one PR, a batch of them, checking on jobs already spawned, or retrieving the data/ a run produced.
---

# Running PRs on OVH

## Overview

A PR's "how to run" section is executed on disposable OVH capacity from an
image CI already built, and whatever its "artifacts" section declares is kept
in Object Storage. Nothing runs on your machine except the agent driving it.

Four properties drive every decision below:

- **Jobs outlive your shell.** `ovh.sh` submits and returns; the job keeps
  running whether or not you are still watching.
- **Quota is CPU summed across live jobs**, not a job count, and exceeding it
  fails outright rather than queueing.
- **Runs resume.** Re-running the same run-id restores what the last attempt
  kept, and the ETLs skip work already on disk.
- **Every knob is an environment variable** read at the bottom of the stack.
  Set them as a prefix on whatever you invoke; they are inherited down through
  `run_prs.sh` → `run_pr.sh` → `ovh.sh`.

## Quick reference

| Task | Command |
|---|---|
| Run specific PRs | `scripts/agent/run_prs.sh <claude\|codex\|pi> 112 115 129` |
| Run every eligible open PR | `scripts/agent/run_prs.sh claude` |
| See the plan without launching | `DRY_RUN=1 scripts/agent/run_prs.sh claude` |
| Run a single PR | `scripts/agent/run_pr.sh claude 112 ovh` |
| What is running right now | `scripts/agent/platforms/ovh_jobs.sh --active` |
| Every job, newest first | `scripts/agent/platforms/ovh_jobs.sh` |
| One job in detail | `scripts/agent/platforms/ovh_jobs.sh <job-id>` |
| Block until a job finishes | `scripts/agent/platforms/ovh_jobs.sh --wait <job-id>` |
| Room left in the quota | `scripts/agent/platforms/ovh_jobs.sh --capacity` |
| Check a prior run before resuming it | `scripts/agent/platforms/ovh_fetch.sh --list pr-112` |
| Job logs | `ovhai job logs <job-id>` |
| List runs in the bucket | `scripts/agent/platforms/ovh_fetch.sh --list` |
| Check what a run kept, with sizes | `scripts/agent/platforms/ovh_fetch.sh --list pr-112` |
| Retrieve just the output | `scripts/agent/platforms/ovh_fetch.sh --only data/ pr-112 .` |
| Stop a job | `ovhai job stop <job-id>` |

## Concurrency: the quota is CPUs, not jobs

The account has **20 CPUs**. Each job draws its `--cpu` against that sum, and a
submission that would exceed it is rejected with `402: quota exceeded` — it
does **not** queue and retry. Memory and disk scale with CPU at 4 GiB RAM and
40 GiB ephemeral disk per CPU, and a single job may request at most 12.

| `OVH_CPU` | Jobs at once | RAM each | Use for |
|---|---|---|---|
| 12 | 1 | 48 GiB | one memory-hungry country |
| 8 (default) | 2 | 32 GiB | safe default for chunk ETLs |
| 5 | 4 | 20 GiB | four PRs, exactly filling the quota |
| 4 | 5 | 16 GiB | many small countries in parallel |
| 2 | 10 | 8 GiB | risks OOM in chunk precompute |

**Those counts assume an empty quota.** Run `ovh_jobs.sh --capacity` first: it
prints free CPU and, for each plausible `OVH_CPU`, how many more jobs fit right
now. Anything already running subtracts.

To work many PRs at once, lower `OVH_CPU` rather than launching more agents:

    OVH_CPU=4 scripts/agent/run_prs.sh claude

`run_prs.sh` sets `OVH_WAIT_CAPACITY`, so a job that finds no room waits for it
instead of failing. Local agents may outnumber OVH slots — an agent spends most
of its life merging main and waiting on CI, holding no quota at all — so raising
`JOBS` above the slot count is reasonable. `JOBS` defaults to
`quota / OVH_CPU`.

`run_prs.sh` **blocks in the foreground until every PR finishes**, which is
hours. Run it under `tmux` or `nohup`; each PR's agent output goes to
`.runs/prs/<pr>.log` and its exit code to `.runs/prs/<pr>.status`. If the
driver dies the OVH jobs continue, but nothing will comment on the PRs.

## API keys

Some countries' sources need a key, declared in the PR body as
`export HIGHLINER_..._API_KEY=...`. The runner image carries no secrets, so the
value has to be forwarded:

    OVH_ENV="HIGHLINER_NLS_API_KEY" HIGHLINER_NLS_API_KEY=… \
        scripts/agent/run_pr.sh claude 125 ovh

`run_prs.sh` does this for you: it reads each PR body for required keys, skips
any PR whose key you have not set (reporting it as `blocked:` rather than
failing an hour into the run), and forwards the ones you do have.

Forwarded values are stored in the job spec and readable afterwards through
`ovhai job get`, so treat them as exposed to anyone with project access.

## Resume

Artifacts are keyed by run-id, and `run_pr.sh` derives it from the PR number
(`pr-112`), so **re-running the same PR resumes it**. A run killed at hour six
restarts near hour six, not at zero.

**Resume covers exactly what the PR's artifacts section declared** — nothing
else. A PR listing `data/<country>/` and `cache/<country>/` resumes both its
output and its DTM cache; one listing only `data/<country>/` re-downloads the
whole terrain set on every attempt. Check the artifacts section before
assuming a re-run will be cheap.

Given restored paths, chunk precompute skips any chunk whose pair parquet
exists, density skips completed zoom files, and cached DTM tiles are reused.

- Force a clean run with `RESUME=0` as a prefix on whatever you invoke.
- Resuming after changing a region's bbox, chunk size, CRS or DTM source is
  **refused**, naming the field that changed — chunks are keyed by grid index,
  so mixing grids would silently produce wrong geography. Delete the region
  directory to rebuild it.
- Restriction outputs are always rebuilt; they are cheap.

### Check the bucket before resuming

Resume trusts what it restores, and skip-if-exists makes a bad prior run
**sticky**: a run that failed in a way that still wrote output leaves files
that the next attempt accepts as finished, then reports success over them.

    scripts/agent/platforms/ovh_fetch.sh --list pr-112

Hundreds of parquet files at an identical size means zero-row output from a run
whose terrain reads were broken — not real results. Launch that PR with
`RESUME=0`, or delete `runs/<run-id>/` from the bucket, before resuming it.

## Behaviour worth knowing before you wait on something

- **Timeout is 7 days**, the platform maximum, set explicitly. A command that
  never exits bills the whole week, so no dev servers in a how-to-run section.
- **Artifacts survive an ordinary failure.** Collection runs in an exit trap,
  so a crashed run still keeps what it produced — that is what makes the next
  attempt resume. A hard `SIGKILL` skips the trap; locally that still leaves
  the streamed `run.log`, but whether anything survives on OVH depends on when
  the Object Storage mount syncs, which is unverified — the platform's
  `SYNC_FAILED` state hints at a sync on finalize.
- **`run.log` is streamed, not collected.** It is `tee -a`'d straight onto the
  mounted bucket as the run goes, which is why it is the one thing likely to
  survive a hard kill, and why it is appended rather than truncated across
  resumed attempts.
- **The image is built from the PR's head commit**, so the branch must be
  merged up to date with main and CI's "Build & push image" job must have
  succeeded on a *branch* push — it does not push on the `pull_request` event.
  This, not OVH, is what serialises the first hour of a batch: merging main
  gives every PR a new head SHA, hence a new image tag CI has to build (~5
  minutes each, staggered by GitHub's concurrency limit).
- **Red CI means no image exists at all.** "Build & push image" needs `check`
  to pass, and is skipped outright when it fails. The driving agent will try to
  reproduce and fix the failure locally, up to 5 attempts, before it can
  schedule anything — so a PR with failing tests spends a long time never
  touching OVH.
- **A PR missing a "how to run" or "artifacts" section is skipped**, not
  guessed at. `run_prs.sh` lists what it skipped.

## Retrieving the data

Artifacts land in `highline-runs@GRA` under `runs/<run-id>/`. `ovh_fetch.sh`
strips that prefix, so paths arrive at their repo-relative position:

    scripts/agent/platforms/ovh_fetch.sh --only data/ pr-112 .   # -> ./data/japan/…

A run usually keeps `cache/<country>/` too — tens of GB of DTM tiles, all
re-downloadable. `--only data/` skips it. Omit `--only` to take everything
including `run.log`. `--only` must come before the run-id.

Check before trusting: `ovh_fetch.sh --list pr-112` shows sizes. An interrupted
run can leave hundreds of identically-sized zero-row parquet files.

## Common mistakes

| Mistake | What happens | Instead |
|---|---|---|
| Reading the concurrency table without checking live usage | `402: quota exceeded` | `ovh_jobs.sh --capacity` first |
| Launching more jobs than the quota fits | Job never created | Lower `OVH_CPU`, or let `OVH_WAIT_CAPACITY` wait |
| Running a PR that needs an API key without setting it | Fails on the worker after CI | `run_prs.sh` blocks it up front; set the key |
| Waiting on a job in one blocking call | Tool timeouts kill the wait, not the job | Re-run `--wait`, or check `--active` later |
| Running `run_prs.sh` in a shell you will close | Driver dies, PRs never get comments | `tmux` / `nohup`; jobs themselves survive |
| Assuming a lost shell killed the job | It runs for up to 7 days, billing | `ovh_jobs.sh --active`, then `ovhai job stop` |
| Leaving `just dev` in a how-to-run | Job never exits, burns the full timeout | Only commands that terminate on their own |
| Re-running to "start fresh" | It resumes instead | `RESUME=0`, or a different run-id |
| Resuming onto a failed run's empty output | Skipped as "done", reports success over nothing | `--list` the run first; `RESUME=0` if suspect |
| Fetching a run to get `data/` | Also pulls tens of GB of `cache/` | `--only data/` |
