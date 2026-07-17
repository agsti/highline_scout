---
name: dispatching-country-etls
description: Use when dispatching country ETL additions from explicit GitHub issue numbers, tracking their issue labels and evidence through review.
---

# Dispatching Country ETLs

## Overview

Orchestrate country additions from explicit GitHub issue numbers. Each issue is
the durable record of ownership, progress evidence, blockers, and review state.
Dispatch only one agent per issue and never infer work from a checklist or a
file-based queue.

## Arguments

One or more explicit `<issue-number>` values. A number identifies the GitHub
issue to work; country names and count-based selection are not accepted.

## Issue state

| Label | Meaning | Applied by |
|---|---|---|
| `etl-country` | eligible country-ETL work item | issue author/triage |
| `in-progress` | an agent owns active implementation | dispatcher |
| `needs-review` | a PR exists and implementation is ready for review | dispatcher |
| `blocked` | work cannot continue without an external decision or change | dispatcher |

## Steps

1. **Preflight** — confirm a clean tree, current default branch, and working
   GitHub authentication. Stop and report any failure before dispatching.
2. **Verify each issue** — run `gh issue view <issue-number>` and confirm it is
   open, titled `ETL: <Country>`, and labelled `etl-country`. Reject duplicate,
   closed, or already-labelled `in-progress`, `needs-review`, or `blocked`
   issues; report the issue URL and reason.
3. **Claim work** — add the `in-progress` label with `gh issue edit` before
   dispatching. Add a comment naming the assigned agent and start time. Record
   the issue URL in the dispatch report.
4. **Dispatch** — launch one isolated worktree agent per verified issue. Give
   it the issue number, URL, country from the title, and the prompt below.
5. **Monitor** — require a GitHub issue update at least every 30 minutes from
   every active agent. Each update must be evidence-bearing: include a command
   and its result, a source URL, a commit SHA, a PR link, or a specific failed
   command and blocker. If the cadence is missed, obtain and post a status
   update before treating the work as complete.
6. **Complete state transition** — verify the reported PR exists with
   `gh pr view <pr-number>`, targets the default branch, and contains
   `Closes #<issue-number>` in its body. Then remove `in-progress`, add
   `needs-review`, and comment with the PR URL and verification evidence. If
   the agent reports an unrecoverable blocker, remove `in-progress`, add
   `blocked`, and comment with the blocker and evidence.
7. **Report** — give the user each issue URL, final label, PR URL (if any),
   and the evidence-backed source/resolution or blocker summary.

## Dispatch prompt template

```text
You are working in an isolated git worktree of the highliner_finder repo.
Implement the country ETL requested by GitHub issue #<issue-number>:
<issue-url> (`ETL: <Country>`).

Rules of engagement:
- Treat the issue as the progress record. Post an evidence-bearing issue comment
  at least every 30 minutes while active, and after source selection, DTM smoke
  result, adapter completion, verification, and PR/blocker. Evidence is a
  source URL, command plus result, commit SHA, PR link, or failed command.
- NEVER ask the user anything. Choose the DTM source, per-region CRS, region
  split, and restriction layers autonomously using the adding-country-etls
  skill. If the best DTM is coarser than 5 m, proceed and flag it in the PR.
- Run Python with `uv run ...`; the plain virtual environment is broken.

Do this:
1. Create and check out branch `etl/<country>-<issue-number>`.
2. Invoke and follow the adding-country-etls skill for <Country>: DTM source
   client, chunk adapter, density adapter, restrictions adapter when a usable
   source exists, and tests. Do not add country-specific Justfile wiring.
3. Verify adapter help, focused tests, `just test && just check`, and a small
   real-chunk DTM smoke test. Do not launch a full national precompute run.
4. Commit, push, and open a PR targeting the default branch. Its body must
   include the source, resolution, method, restrictions, coverage summary, and
   `Closes #<issue-number>`.
5. Post the PR link and evidence-bearing completion comment on the issue.

If an unrecoverable blocker occurs, do not open a PR. Post its evidence and
required next action to the issue, then report it in your final message.
```

## Common mistakes

| Mistake | Consequence |
|---|---|
| Dispatching before applying `in-progress` | ownership race and duplicate work |
| Accepting a PR without checking its closing reference | issue stays open after merge |
| Status-only comments without command/source/commit evidence | no auditable progress record |
| Missing the 30-minute update cadence | maintainers cannot distinguish active work from a stall |
| Labelling a blocker `needs-review` | review queue contains work that cannot merge |
