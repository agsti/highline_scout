---
name: dispatching-country-etls
description: Use when batch-dispatching new country ETL work from COUNTRIES.md — taking N pending countries, running an autonomous subagent per country in its own worktree, and tracking progress markers through to open PRs.
---

# Dispatching Country ETLs

## Overview

Orchestrates parallel country additions: pick N `[ ]` countries from
`COUNTRIES.md`, mark them `[O]` on `main`, dispatch one background worktree
subagent per country running the `adding-country-etls` skill, and flip each to
`[P]` on `main` as its PR opens. The PR branch itself flips the line to `[X]`,
so merging a PR completes the cycle.

State machine (one line per country in `COUNTRIES.md`):

| Marker | Meaning | Who writes it | Where |
|---|---|---|---|
| `[ ]` | todo | — | main |
| `[O]` | agent dispatched | this skill, at dispatch | main |
| `[P]` | PR open | this skill, on subagent completion | main |
| `[X]` | done | subagent, inside its PR branch | PR → merged to main |

## Arguments

`<count>` (default 1) and/or explicit country names. Explicit names override
count-based selection.

## Steps

1. **Preflight** — on `main`, clean tree, `git pull`, `gh auth status` OK.
   Any failure: stop and report; do not dispatch.
2. **Select** — the first `<count>` lines matching `- [ ] ` in `COUNTRIES.md`
   (top-to-bottom), or the explicitly named countries (each must currently be
   `[ ]`; skip and report any that aren't).
3. **Mark ongoing** — change each selected line to `- [O] `, commit to `main`
   (`chore: mark <countries> ETL ongoing`), push. Push BEFORE dispatching so
   subagent branches fork from a base that already has `[O]` — their `[X]`
   edit then diffs cleanly against it.
4. **Dispatch** — one `Agent` call per country, all in a single message:
   `subagent_type: general-purpose`, `isolation: "worktree"`,
   background (default). Prompt = the template below verbatim, with
   `<Country>`/`<country>` substituted.
5. **On each completion** — verify the PR really exists:
   `gh pr list --head etl/<country>`. If yes: on `main`, flip that line
   `[O]` → `[P]`, commit (`chore: mark <country> ETL PR open`), push.
   If no PR: flip back to `[ ]`, commit, push, and report the subagent's
   final message to the user. Never mark `[P]` on the agent's say-so alone.
6. **Report** — per country: PR URL, DTM source/resolution, and any
   shortfalls the subagent flagged (coarse DTM, missing restriction layers).

## Dispatch prompt template

```text
You are working in an isolated git worktree of the highliner_finder repo.
Add <Country> to the highliner ETL pipeline, end to end, fully autonomously.

Rules of engagement:
- NEVER ask the user anything (no AskUserQuestion, no pausing for input).
  Every choice — DTM source, per-region CRS, region split, restriction
  layers — you make yourself following the skill's selection rules. If the
  best available DTM is coarser than 5 m, proceed anyway and flag it in the
  PR body.
- Run python via `uv` (`uv run ...`); the plain venv is broken.

Do this:
1. Create and check out branch `etl/<country>`.
2. Invoke the `adding-country-etls` skill and follow it completely for
   <Country>: DTM source client, chunk adapter, density adapter,
   restrictions adapter (if a usable source exists), justfile ETL_COUNTRIES
   wiring, tests.
3. Verify per that skill: `--help` smoke tests for each adapter,
   `just test && just check`, and a small real-chunk smoke test of the DTM
   source. Do NOT launch the full national precompute/density run — that
   happens after merge.
4. In COUNTRIES.md, change the `<Country>` line marker to `[X]`, keeping the
   rest of the line intact.
5. Commit with a conventional message, push the branch to origin, and open a
   PR with `gh pr create` targeting main. PR body: the end-of-skill summary
   (source, resolution, method, restrictions overview, coverage km²), ending
   with the standard Claude Code footer.
6. Your final message: the PR URL, then the same summary.

If you hit an unrecoverable blocker (no usable licensed DTM at any
resolution, auth failure), do NOT open a PR; report the blocker as your
final message instead.
```

## Merging PRs (conflict rule)

Each PR changes its country's line `[O]` → `[X]` while `main` has since moved
it to `[P]` — expect a one-line conflict in `COUNTRIES.md` at merge time.
Resolution is always: keep `[X]`.

## Common mistakes

| Mistake | Consequence |
|---|---|
| Dispatching before pushing the `[O]` commit | PR base lacks `[O]`; messier diff/conflicts |
| Marking `[P]` without `gh pr list` verification | main claims a PR that doesn't exist |
| Letting the subagent run the full national precompute | hours-long run + 10s of GB inside a throwaway worktree |
| Selecting countries already `[O]`/`[P]` | two agents on one country, duplicate PRs |
| Forgetting to flip failed countries back to `[ ]` | country stuck `[O]`, never re-dispatched |
