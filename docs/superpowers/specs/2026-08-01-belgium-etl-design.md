# Belgium ETL design

Belgium will be represented by two precompute regions in Belgian Lambert 72
(EPSG:31370), using the public 1 m terrain products published by the regions.
Flanders (including the Brussels coverage in the source envelope) uses the
DHMV II bare-earth WCS, resampled server-side to the pipeline's 5 m analysis
grid. Wallonia uses the openly licensed 1 m LiDAR MNT bulk GeoTIFFs, cached by
province and selected by the requested chunk bounds.

The country packages for chunk precompute, density, and restrictions follow the
existing country-adapter convention. Restrictions build the shared Natura 2000
Birds and Habitats overlays from the Belgian public register, retaining the
existing `zepa` and `zec` display and density-mask semantics.

The work adds focused tests for CLI registration, WCS multipart GeoTIFF
extraction, source no-data behavior, cached bulk sheets, and restriction
directive filtering. A run produces country-scoped outputs below
`data/belgium/` and reusable terrain sheets below `cache/belgium/`.
