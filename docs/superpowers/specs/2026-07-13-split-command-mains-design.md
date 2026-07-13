# Split command mains design

## Goal

Replace the mixed `highliner` command dispatcher with four focused command
modules. Each command module owns its argument parsing, progress reporting, and
startup logic; application and ETL services remain in their existing layers.

## Command modules

- `highliner.server.main` starts FastAPI through Uvicorn. It owns the
  `--data-dir`, `--host`, and `--port` options.
- `highliner.etl.chunk.main` runs region chunk precomputation. It owns the
  precompute options, region-default resolution, elapsed/ETA reporting, and
  invocation of `etl.services.precompute`.
- `highliner.etl.density.main` builds density data. It owns the density options,
  elapsed reporting, and invocation of `etl.services.density`.
- `highliner.restrictions.main` builds national protected-area layers. It owns
  its parser, status output, and invocation of the restrictions repository.

Each module exposes `main(argv: list[str] | None = None) -> None` to keep the
commands directly testable without subprocesses. CLI-only helpers live beside
the command that uses them; no module imports command handlers from another
command module.

## Packaging and callers

The package exposes four console scripts:

- `highliner-server`
- `highliner-etl-chunk`
- `highliner-etl-density`
- `highliner-restrictions`

`highliner/cli.py` and the legacy `highliner` console script are removed. The
Just recipes and current user-facing documentation use the replacement command
names.

## Tests

CLI tests move from the central dispatcher to their owning command modules.
They retain the existing behavior checks for precompute defaults, chunk worker
forwarding, and density output location. New focused tests cover server startup
arguments and restriction-layer invocation. The full Python quality suite
continues to validate type checking, linting, dead-code detection, and tests.

## Scope

This is a command-interface refactor only. Service APIs, output data layout,
and FastAPI routes do not change.
