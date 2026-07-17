# Country ETL Issue Tracking Design

## Goal

Make implementation progress for every new country ETL visible and durable,
while allowing multiple country additions to proceed without shared-file
coordination conflicts.

## Tracking model

`COUNTRIES.md` is a static candidate list. It does not contain mutable status
markers. A GitHub issue is the canonical work record for one country, and a PR
is its review record.

Before dispatching a country, create one issue labelled `etl-country` and
`in-progress`. The body contains these checkboxes:

- DTM source and reuse licence selected
- DTM smoke chunk validated
- Chunk, density, and applicable restrictions adapters implemented
- Tests and static checks passed
- Pull request opened

The dispatcher must first search for an open `etl-country` issue for the
country. An existing issue means the country is already owned and must not be
dispatched again.

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
`dispatching-country-etls` is rewritten to select candidates from the static
list, create and validate issues, dispatch independently, and report issue and
PR links. Its old shared-file marker state machine is removed.

## Validation

Review the skill text for all required checkpoints, interval, labels, duplicate
prevention, blocker handling, PR closing syntax, and the absence of mutable
`COUNTRIES.md` status edits. Run a realistic dispatch scenario against the
revised text and confirm the proposed workflow satisfies each condition.
