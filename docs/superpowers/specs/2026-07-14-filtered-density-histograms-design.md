# Filtered Density Histograms Design

## Goal

Make the zoomed-out density heatmap honour the live length, exposure, and
protected-area exclusion filters without reading candidate parquet files at
request time.

## Scope

This changes the offline density pyramid, its CLI, `GET /density`, and the
frontend density request. It does not change candidate extraction, zone
clustering, the restriction overlay UI, or the visible density styling.

## Data model

The density ETL will retain a sparse histogram for every slippy-map cell at
each configured density zoom. A candidate contributes to the tile containing
its midpoint. Its histogram key has three components:

1. a 10 m length bucket;
2. a 10 m exposure bucket;
3. a three-bit restriction mask.

Buckets are indexed by `floor(value / 10)`. Slider bounds are snapped upward to
the next bucket boundary before a request is evaluated: a 12–98 m length range
uses the 20–100 m buckets, and a 12 m minimum exposure uses the 20 m-and-up
buckets. This deliberately coarse rule keeps the 1 m sliders deterministic
without making a proportional estimate from histogram counts. A candidate
exactly on a 10 m boundary belongs to the higher bucket.

Restriction-mask bits are assigned in the stable `LAYERS` registry order:
`zepa=1`, `zec=2`, and `enp=4`. For each layer, a bit is set when either UTM
anchor is covered by at least one polygon in that country’s stored restriction
parquet. Boundary points count as restricted (`covers` semantics). A candidate
inside multiple layer types has multiple bits, so overlaps are represented once
and any enabled-layer combination remains exactly queryable.

Each JSON cell stores its tile coordinates plus a sparse list of histogram
rows. It continues to carry total count, maximum exposure, and length bounds
for compatibility and tooltip metadata. Empty bucket/mask combinations are not
written.

## ETL and country scope

`highliner-etl-density` will take `--country`, defaulting to
`config.DEFAULT_COUNTRY`, and resolve the selected region through the existing
country-aware region lookup. The builder receives the country data root and
loads `<data-dir>/<country>/restrictions/<layer>.parquet` for every registered
layer that exists. Missing country restriction files behave as empty layers.

Restriction polygons are transformed from their stored WGS84 CRS into the
region grid CRS before anchor containment is evaluated. The builder creates a
spatial index per loaded layer, first reduces candidate polygons by bounds, and
then applies precise point coverage. This preserves the current static-density
read path while keeping work offline.

## API and frontend flow

`GET /density` gains the zone-equivalent `min_len`, `max_len`, and
`min_exposure` query parameters, plus `exclude_layers` as a comma-separated
list of layer IDs. It retains `country`; when region is omitted it continues
to merge only density layers from that country.

For each viewport-visible cell, the endpoint sums histogram rows whose length
and exposure buckets overlap the requested filter intervals and whose mask has
no bit in the enabled exclusion mask. It returns the resulting `n_pairs` and
omits zero-count cells. Existing legacy JSON rows without histograms remain
readable only for the unfiltered request; a filtered request will not claim a
false filtered result from legacy summary data.

The map’s density request includes the same length and exposure settings sent
to `/zones`. When restriction mode is `exclude`, it also includes the enabled
restriction layer IDs; informative mode supplies no exclusions. Therefore the
heatmap represents the same eligible candidate population as the detailed zone
view.

## Errors and compatibility

Unknown `exclude_layers` IDs are ignored consistently with the restriction
endpoint. A missing density directory keeps its current 404 behaviour. A
missing country restriction directory does not fail density generation. Since
histograms require a fresh density precompute, stale legacy files continue to
serve their existing unfiltered totals but must be regenerated to support live
filtered density.

## Precompute performance

Density building is parallelizable by candidate parquet file. The density CLI
will accept --workers, defaulting to one exactly like the chunk precompute
command. With more than one worker it starts a ProcessPoolExecutor; every
process loads and reprojects the selected country's restriction layers once
through an initializer, then processes a disjoint batch of candidate partition
files. Each worker returns partial per-cell summaries and sparse histogram
counts, which the parent merges before writing the same deterministic JSON.

JSON assembly will keep histogram rows grouped by cell while aggregating, rather
than scan the full histogram map once for every cell. Output work is therefore
linear in histogram rows rather than quadratic in cells times rows. Worker
counts stay explicit because every process holds transformed country restriction
geometries in memory.

## Tests

Backend tests will prove 10 m length/exposure bucket aggregation and exact
range totals; country-scoped restriction loading; either-anchor containment;
boundary containment; multi-layer overlap masks; exclusion combinations; zero
filtered cells; and legacy unfiltered compatibility. CLI tests will prove
`--country` is forwarded. Frontend tests will prove density requests include
the live filters and include selected restriction IDs only in exclusion mode.
