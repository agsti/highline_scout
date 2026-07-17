# Country ETL Issue Tracking Design

## Goal

Make implementation progress for every new country ETL visible and durable,
while allowing multiple country additions to proceed without shared-file
coordination conflicts.

## Tracking model

The dispatch workflow is independent of `COUNTRIES.md`. A GitHub issue is the
canonical work record for one country, and a PR is its review record.

Before dispatching a country, locate its open country issue, then add the
`in-progress` label. Every country issue has the `etl-country` label and this
checkbox body:

- DTM source and reuse licence selected
- DTM smoke chunk validated
- Chunk, density, and applicable restrictions adapters implemented
- Tests and static checks passed
- Pull request opened

The dispatcher searches for an open `etl-country` issue for the country. A
missing issue is an error: reconcile the backlog before dispatching. An issue
already labelled `in-progress` or `needs-review` is already owned and must not
be dispatched again.

## Backlog reconciliation

`scripts/sync_country_etl_issues.py` is the only workflow component that reads
`COUNTRIES.md`. It parses checklist lines and, for every country not marked
`[X]`, creates a country issue unless an open `etl-country` issue already
exists for that country. It never edits `COUNTRIES.md`, closes issues, changes
labels, or creates duplicates. The script supports a dry run by default and an
explicit apply flag, uses `gh` authentication, and prints the created and
already-existing issue URLs.

The legacy `[O]` and `[P]` markers may remain in the file for migration, but
the reconciliation script treats every non-`[X]` line as unfinished. They have
no effect on dispatch or issue state.

## Progress contract

The implementing agent comments on its issue after each completed checkpoint,
including relevant commit SHA or command evidence. While actively working, it
posts a concise update at least every 30 minutes. On a blocker, it posts a
final evidence-based comment, replaces `in-progress` with `blocked`, and does
not open a PR.

## Completion flow

An agent works on `etl/<country>` and opens a PR containing `Closes #<issue>`.
It replaces `in-progress` with `needs-review` when the PR is open. GitHub
closes the issue when the PR merges. Agents do not edit `COUNTRIES.md`.

## Skill changes

`adding-country-etls` gains the progress contract for a country implementation.
`dispatching-country-etls` is rewritten to dispatch explicitly named open
issues, validate ownership, and report issue and PR links. It does not select
or mutate entries in `COUNTRIES.md`. The new reconciliation script creates the
initial country issues from that file.

## Validation

Test the reconciliation script against fixture Markdown and mocked `gh`
responses: it must recognize every non-`[X]` line, skip each existing open
issue, create only missing issues, and make no changes during a dry run. Review
the skill text for all required checkpoints, interval, labels, duplicate
prevention, blocker handling, PR closing syntax, and dispatch independence from
`COUNTRIES.md`. Run a realistic dispatch scenario against the revised text and
confirm the proposed workflow satisfies each condition.
