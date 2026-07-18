# Worktree shared directories

## Goal

Document the required setup for an isolated Git worktree without duplicating
large, shared development assets.

## Design

The existing setup guidance in `AGENTS.md` will retain its requirement for a
separate, worktree-local `.venv`, because virtual-environment paths are tied to
the checkout that created them.

It will additionally require each worktree to symlink `cache/`, `data/`, and
`frontend/node_modules/` to the corresponding directories in the primary
checkout. These directories are shared intentionally: terrain cache and
precomputed data are large, while Node dependencies need not be installed once
per worktree.

## Scope and verification

Only `AGENTS.md` changes. Verification is a readback of the edited setup
paragraph; no runtime behavior changes.
