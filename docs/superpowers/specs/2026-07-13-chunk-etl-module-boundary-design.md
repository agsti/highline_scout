# Chunk ETL module boundary

## Goal

Make `highliner.etl.chunk` own every implementation module used exclusively by
the chunk-precompute command, while leaving genuinely shared ETL and server
code in their existing packages.

## Package layout

Move these modules into `highliner/etl/chunk/`:

- `precompute.py` — chunk orchestration and partition writing
- `terrain.py` — raster anchor extraction
- `pairing.py` — candidate-pair generation
- `dtm.py` — terrain tile download and raster construction
- `anchors.py` — anchor parquet writer
- `candidates.py` — candidate parquet writer

`main.py` remains the console-script entry point. The resulting chunk package
has no dependency on the generic `highliner.etl.services` or
`highliner.etl.repositories` packages.

## Boundaries retained

`highliner.etl.density` remains outside the chunk package because it is a
separate command that reads completed pair partitions through the server read
layer. `highliner.etl.repositories.restrictions` remains outside because it
serves the separate restrictions builder command.

Shared `highliner.core` configuration/region helpers and `highliner.models`
domain types stay shared; moving them would expand the refactor beyond the
chunk command boundary.

## Migration and compatibility

All production imports and tests move to the new chunk-package paths. The old
chunk-only modules are deleted rather than left as compatibility re-exports:
they are internal implementation paths and retaining them would leave the
ownership boundary ambiguous. The `highliner-etl-chunk` console-script target
remains `highliner.etl.chunk.main:main`, so its external invocation is
unchanged.

## Verification

Run the affected chunk ETL tests first, then the full backend suite and the
repository checks. Confirm there are no remaining imports of the deleted
chunk-only modules and that the console-entry-point assertion remains valid.
