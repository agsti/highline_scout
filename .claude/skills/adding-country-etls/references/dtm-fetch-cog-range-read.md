# Pattern 4: Cloud-Optimized GeoTIFF range reads + local resample

Use when the source publishes large COGs behind a spatial catalog (STAC or
Atom) and downloading whole sheets would be wasteful (multi-GB per sheet).
rasterio/GDAL range-reads (`rasterio.windows.from_bounds`) pull only the
blocks covering the chunk's bbox — average-resampled to 5 m and cached by
bbox hash, giving a much smaller cache footprint than pattern 3's whole-sheet
downloads.

**Reference implementations:**
- `austria/dtm_bev.py` (BEV ALS-DTM): Atom catalog of 55 large EPSG:3035
  COGs; range-reads + resamples a 5 m subset per chunk, caches the subset
  keyed by `(url, bbox)` hash.
- `switzerland/dtm_swissalti.py` (swissALTI3D): STAC catalog with historical
  snapshots — keeps the newest 2 m asset per tile (`_latest_assets`),
  downloads with a thread pool (8 workers), resamples to 5 m.

## Hybrid variant

`united_kingdom/dtm_ea.py` (EA LIDAR England) mixes this with pattern 3:
downloads whole 5 km 1 m zip tiles (not range reads — EA doesn't publish
COGs) but only for tiles a pre-queried catalog confirms exist, avoiding
wasted requests on sea/gap tiles. It then locally average-resamples each
tile to 5 m and discards the 1 m source, caching only the small 5 m result.
Read this one if your source is catalog-gated but not COG-backed.

## Key technique: windowed range read

```python
with rasterio.open(url) as src:  # GDAL issues HTTP range requests here
    window = from_bounds(*bbox, transform=src.transform).round_offsets()
    data = src.read(1, window=window, out_shape=(height, width),
                    masked=True, resampling=Resampling.average)
```
No whole-file download ever happens — GDAL's `/vsicurl`-style reader (used
transparently when `rasterio.open` gets a URL) fetches only the byte ranges
covering the requested window.
