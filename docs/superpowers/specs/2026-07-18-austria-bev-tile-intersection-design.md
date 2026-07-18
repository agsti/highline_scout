# Austria BEV Tile Intersection Design

## Goal

Prevent Austria chunk precompute from selecting an adjacent BEV elevation COG
whose raster does not overlap the requested EPSG:3035 chunk, while preserving
the existing cache and resumable partition behavior.

## Evidence

Carinthia stopped with `rasterio.errors.WindowError` while intersecting the
requested window with a BEV COG. The failing halo ended at easting 4,649,050,
but the selected COG starts at easting 4,650,000, leaving a 950 m gap. Its
catalogue longitude/latitude bounding box nevertheless intersected the
transformed chunk bounding box.

The catalogue currently reduces each projected tile footprint to an
axis-aligned WGS84 bounding box. EPSG:3035 grid cells become rotated,
non-axis-aligned shapes in WGS84, so adjacent cells' bounding boxes overlap.
That lossy intersection test caused 37 of Carinthia's 252 partitions to fail;
the other 215 partitions completed and remain reusable.

## Options Considered

1. Filter using the native EPSG:3035 grid coordinates encoded in BEV COG
   filenames (selected). This is exact for the source product, avoids remote
   raster opens for false matches, and does not change the catalogue cache.
2. Persist exact GeoRSS polygons. This avoids relying on filenames but requires
   a catalogue schema migration and still performs selection in transformed
   coordinates.
3. Catch empty Rasterio windows and skip them. This prevents the crash but
   retains incorrect tile selection and needless remote metadata reads.

## Design

The Austria DTM adapter will recognize the BEV filename fields
`CRS3035RES50000mN<northing>E<easting>` and derive that COG's 50 km square in
EPSG:3035. Before materializing subsets, `fetch_bev_tiles` will transform the
requested bbox geometry to EPSG:3035 and require intersection with this native
tile square in addition to the existing catalogue check.

The native check applies to official BEV URLs matching the product naming
contract. An unrecognized URL retains the existing catalogue-based behavior,
so test doubles and a future provider URL change do not silently eliminate all
terrain. Existing subset paths and hashes remain unchanged.

No completed partitions or cached TIFF subsets need deletion. Once fixed, a
run starting at Carinthia will skip existing pair partitions, compute the 37
unfinished partitions, and continue with later regions.

## Testing and Verification

Add a regression test with two catalogue entries whose WGS84 bounding boxes
both appear to overlap a chunk. Their BEV filenames identify adjacent native
tiles; only the genuinely intersecting EPSG:3035 tile may be materialized.
Watch this test fail against the current implementation before adding the
filter.

Then run the focused Austria DTM tests, the complete backend test suite, and
`just check`. A read-only inspection of Carinthia's output will confirm that
the existing 215 finished partitions remain untouched and resumable.

## Scope Boundaries

This change does not alter the BEV catalogue download, raster resampling,
nodata handling, chunk geometry, anchor extraction, pair generation, region
bounds, or output formats. It does not delete or rewrite user-generated ETL
data.
