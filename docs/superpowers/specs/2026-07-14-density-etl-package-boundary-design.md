# Density ETL package boundary

## Goal

Make `highliner.etl.density` the home of all density-specific offline
calculation code, while retaining genuinely shared helpers in their existing
shared packages.

## Package layout

`highliner.etl.density` will contain:

- `main.py`: the `highliner-etl-density` command-line entry point.
- `builder.py`: `build_density`, midpoint conversion, aggregation, progress
  reporting integration, and density JSON output.
- `candidates.py`: the one-pass parquet-to-`Candidate` materializer used only
  by the density builder.

The density builder will import its local candidate materializer rather than
`highliner.server.repositories.candidates`.

## Shared dependencies

`highliner.core.tiles` remains in `core`, because both the offline builder and
the `/density` endpoint use the slippy-map tile conversion functions.

`highliner.server.repositories.chunked_store.read_grid` also remains in the
server read layer because server endpoints use it to read region metadata. The
density builder may continue to use that shared reader to obtain a region CRS.

## Removed modules

`highliner.etl.services.density` and
`highliner.server.repositories.candidates` will be removed. Their tests and all
imports will point to the density package instead.

## Compatibility and verification

The `highliner-etl-density` entry point and generated density JSON schema are
unchanged. Tests will cover the new module paths, CLI invocation, density cell
aggregation, and empty candidate partitions. The targeted tests and repository
quality checks will run after the move.
