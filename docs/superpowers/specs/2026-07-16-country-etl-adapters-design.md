# Country ETL adapters

## Goal

Make country-specific ETL configuration explicit and repeatable without
embedding country branches in reusable ETL code. Spain is the first adapter;
adding a country later should mean adding its adapter modules and listing it in
the Justfile.

## Package boundaries

ETL code moves from `highliner.etl` to `highliner.etls`.

Each ETL family has a shared implementation and one module per supported
country:

```
highliner/etls/
  chunk/
    shared.py
    spain.py
  density/
    shared.py
    spain.py
  restriction/
    shared.py
    spain.py
```

Every country module exports `main()`. It owns only country configuration:
the country ID, its regions and their bounding boxes, CRS and terrain-source
selection, and (for restrictions) country-specific source parsing. The shared
modules contain no country-name conditionals.

## Chunk ETL

`chunk.shared` receives `country` explicitly along with each region's name,
bbox, CRS, terrain source, data directory, cache directory, and worker count.
It writes to `data/<country>/<region>` and uses `cache/<country>` as necessary.
It does not infer a country from a region name.

`chunk.spain:main` supplies `COUNTRY = "spain"` and the existing Spanish
region catalogue, then calls the shared workflow. Its command-line options
preserve the current operational controls such as selecting/resuming regions,
parallel region jobs, and chunk workers.

## Density ETL

Density becomes country-scoped rather than region-scoped. The shared density
workflow discovers all region directories under `data/<country>/` that contain
`grid.json`, then builds density for each. It continues to pass the matching
country restrictions directory to the existing density builder.

`density.spain:main` passes its country constant. It has no `--region`
argument. The worker option retains its existing meaning: concurrent pair-file
batches within each region; regions themselves run sequentially.

## Restriction ETL

`restriction.spain:main` is a distinct entry point. It owns Spain's MITECO
source locations, raw-input layout, and ZEPA/ZEC designation extraction.
Reusable reading, normalization, simplification, and parquet-writing pieces
live in `restriction.shared` and take paths/specifications explicitly. Running
restrictions is independent from chunk precompute, so resumed chunk work does
not rebuild national layers.

## Commands and Just recipes

Console-script targets point directly to the country adapter `:main`
functions. The Justfile declares the supported country IDs once and provides
three recipes, each processing those countries sequentially:

- `etl-chunk-8` invokes each country chunk adapter with eight chunk workers.
- `etl-density-8` invokes each country density adapter with eight workers.
- `etl-restriction` invokes each country restriction adapter.

With Spain as the only configured country, these recipes retain the present
Spain outputs. Adding another country consists of creating its country adapter
modules and adding its ID to the Justfile country list; shared code remains
unchanged.

## Tests and migration

Tests will establish that Spain adapters pass `"spain"` and correct
configuration to shared workflows, chunk paths and caches use the explicit
country, density discovers all eligible country regions without a region
argument, and restriction adapters delegate Spain-specific inputs to shared
writers. Existing CLI and import tests will be updated to the new module paths
and console-script targets. No data migration is required because the on-disk
layout remains `data/spain/...` and `cache/spain/...`.
