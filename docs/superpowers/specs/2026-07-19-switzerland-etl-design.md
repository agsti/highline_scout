# Switzerland ETL Design

## Scope

Add Switzerland to the offline chunk, density, and protected-area pipelines.
The server remains unchanged because it discovers country and region outputs
from `data/<country>/<region>/grid.json`.

## Terrain source and coverage

Use swisstopo swissALTI3D, a bare-earth model published as 1 km square Cloud
Optimized GeoTIFF tiles in LV95/LN02 (EPSG:2056). Select the 2 m assets: they
are finer than the project's 5 m baseline, while the 0.5 m variant would make
national cache and per-chunk memory costs impractical. The swisstopo free
basic-geodata terms permit reuse for all purposes with source attribution.

A dedicated `dtm_swissalti.py` client will query the official paginated STAC
API for a chunk's WGS84 bounds, choose the newest 2 m snapshot for each stable
1 km tile id, cache the query result, and download each COG once under the
country cache. Downloads use bounded parallelism, process-safe file locks,
transient retry/backoff, `.part` files, and GeoTIFF header validation.
swissALTI3D encodes nodata as `-9999`, already normalized by the shared raster
merge path; an empty catalogue result is valid outside national coverage.

Use one national region named `switzerland` in EPSG:2056. Its bbox,
`(2485000, 1075000, 2834000, 1296000)`, is the 2026 swissBOUNDARIES3D Swiss
national-territory extent rounded outward to 1 km. A single region avoids
duplicating terrain across overlapping canton bounding boxes. It produces 805
10 km chunks (80,500 km2 of rectangular grid coverage versus about 41,291 km2
of national territory); border chunks without catalogue tiles are harmless.

## Adapters and restrictions

The chunk CLI follows the existing single-region Czechia adapter and forwards
country, bbox, CRS, cache, workers, and `swissalti3d` source to shared
precompute. The density CLI is the normal thin country wrapper.

The FOEN restriction adapter downloads three official EPSG:2056 shapefile
archives from `data.geo.admin.ch`, flattens them into the raw cache, reprojects
to EPSG:4326, and writes:

- `ch_game_reserves`: federal hunting-ban/game reserves, including integral
  and partial protection zones for mammals and birds;
- `ch_bird_reserves`: federal waterbird and migratory-bird reserves;
- `ch_parks`: the Swiss National Park and parks of national importance.

All three receive English backend metadata and Catalan/Spanish frontend text.
The copy will tell scouts to check the reserve object provisions, canton, or
park management before rigging rather than implying a blanket national rule.

## Failure handling and tests

Catalogue/network failures are raised so chunks remain retryable; only genuine
empty catalogue results become no-terrain chunks. Unit tests cover STAC
pagination/latest-version selection, cached/download dispatch, adapter
forwarding, restriction source loading, and translation highlight invariants.
A real Lauterbrunnen-area chunk will validate the 2 m raster, `-9999` nodata,
and anchor/pair output without starting a national run.
