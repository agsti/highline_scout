# Pattern 3: Bulk national archive/sheet download, cached, read locally per chunk

**Preferred pattern** whenever the agency publishes a bulk sheet/archive
product (per the skill's requirements: bulk over tiled WCS). The source is
downloaded once into `cache_dir` — a catalog crawl/query plus the sheet
downloads, locked with `fcntl.flock` so concurrent `--workers` don't race —
and every chunk afterwards is a local intersection test + read, with no
per-chunk network traffic.

**Copy `czechia/dtm_cuzk.py` as the reference shape** (catalog cache +
per-sheet zip download + flock is the most common variant). Other
implementations, for variations on the theme:

- `spain/dtm_cnig.py` (CNIG MDT05): scrapes a paginated download-portal
  catalog for sheet IDs intersecting the bbox (cached to disk), downloads
  each GeoTIFF sheet through a multi-step portal flow
  (`detalleArchivo` → `initDescargaDir` → `descargaDir` POST).
- `france/dtm_rgealti.py` (RGE ALTI): catalog crawl maps departments to
  archive names; downloads one resumable 7z per department (Range-resume),
  extracts and converts ASC dalles to GeoTIFF, selects local dalles per
  chunk.
- `italy/dtm_hrdtm.py` (HR-DTM-5m): simplest case — one ~22 GB national
  GeoTIFF, downloaded once (Range-resumable, size-verified), every chunk
  just does a local windowed read. No bbox/CRS-aware fetch at all.
- `united_kingdom/dtm_os.py` (OS Terrain 50 / OSNI): one national zip
  downloaded once, sheets extracted and spatially indexed (JSON bounds
  index) for fast local lookup per chunk. OSNI additionally converts raw XYZ
  point clouds into GeoTIFF itself.

## Common building blocks across these

- **Catalog cache**: resolve which sheets/archives intersect the bbox once
  (Atom feed, portal scrape, or WFS query), cache the resolution to disk
  keyed by bbox hash or as one full index, under an `fcntl.flock` so
  concurrent workers share one crawl instead of racing.
- **Sheet download**: stream to a `.part` file, `Range`-resume on retry for
  large archives, `.replace()` onto the final path only once complete —
  never leaves a half-written file at the real destination.
- **Completion markers**: for multi-step extractions (RGE ALTI's per-
  department 7z), write a marker file last so a killed extraction restarts
  cleanly rather than resuming from a half-extracted state.

Every fetcher in this pattern must explicitly convert or carry through the
source's nodata/sea sentinel to a fixed value (typically `-9999.0`) during
local conversion — see the "Common mistakes" table in SKILL.md.
