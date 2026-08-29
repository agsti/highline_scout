# Luxembourg ETL Implementation Plan

**Goal:** Add Luxembourg chunk, density, and protected-area ETL adapters.

**Architecture:** Cache the official LiDAR 2019 0.5 m DTM ZIP and extract its
GeoTIFFs once; use EPSG:2169 for the national region. Build SPA, SAC, and ZPIN
overlays from the Luxembourg Open Data portal, then register their layer bits
and translations.

## Tasks

1. Write failing tests for the cacheable DTM fetcher and region adapter.
2. Implement the DTM fetcher and Luxembourg chunk CLI.
3. Add the density adapter and its command-entry tests.
4. Write failing restrictions tests, then implement official-source downloads.
5. Register restriction layers, translations, and density bits; run full checks.
