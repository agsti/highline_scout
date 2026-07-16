# Country-scoped restriction layers

## Goal

Expose and use only the protected-area layer files generated for the selected
country. A country can use different layer identifiers and may not have every
globally known restriction type.

## Design

The directory `data/<country>/restrictions/` is the source of truth for a
country's available layers. The server will identify its available layers by
intersecting existing `*.parquet` filenames with the shared `LAYERS` metadata
registry.

`GET /restrictions/layers?country=<country>` will return metadata only for that
country's available files. `GET /restrictions` will use the same available set:
an omitted `layers` parameter selects all available layers and supplied IDs are
ignored unless they are available for the requested country. Missing country
data remains a successful empty response.

The frontend already refetches layer metadata and resets selected layers when
the country changes. With the country-filtered metadata response, its controls,
legend, selected IDs, overlay request, and exclusion logic will therefore use
only that country's restrictions without a UI-specific country registry.

The density ETL's country orchestration already passes
`data/<country>/restrictions`. The lower-level density builder will no longer
silently default to Spain; when no directory is provided, it will derive the
country directory from the region path under the configured data root. Explicit
`restrictions_dir` remains supported for callers and tests.

## Error handling

Unknown countries, countries without restriction output, and missing layer
files yield no layers/features rather than errors. Unknown requested layer IDs
are ignored. Metadata registry entries without a matching country file are not
shown.

## Tests

- API metadata returns only the existing layer files for the requested country.
- Viewport restriction reads do not serve a registry layer absent from that
  country.
- Standalone density builds derive and use the restriction directory belonging
  to their region's country rather than Spain.
- Existing frontend country-change behavior continues to enable only the API
  metadata it receives.

## Scope

No changes to the on-disk restriction ETLs, density file format, shared display
metadata, localization, or the visual layout are required.
