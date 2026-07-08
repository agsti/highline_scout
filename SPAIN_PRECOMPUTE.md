# Precompute inputs for the rest of Spain

This is the information needed by `NEW_LOCATIONS.md` to extend precompute
beyond Catalonia. It is a planning/input inventory, not yet an executable
implementation: the current code still assumes the ICGC WCS and a single global
`EPSG:25831` CRS.

## Terrain source

Primary national source: IGN/IDEE `MDT05` from PNOA LiDAR, first coverage.

- Product: Digital Terrain Model, 5 m mesh.
- License/attribution: CNIG/IGN open data terms, CC-BY-compatible attribution.
- Metadata/download page:
  `https://centrodedescargas.cnig.es/CentroDescargas/catalogo.do?Serie=MDT05`
- OGC API Coverages landing page:
  `https://api-coverages.idee.es/collections`
- Peninsula and Balearics 5 m coverage:
  `EL.ElevationGridCoverage_25830_5_PB`
  `https://api-coverages.idee.es/collections/EL.ElevationGridCoverage_25830_5_PB?f=json`
- Canary Islands 5 m coverage:
  `EL.ElevationGridCoverage_4083_5_C`
  `https://api-coverages.idee.es/collections/EL.ElevationGridCoverage_4083_5_C?f=json`
- Bulk fallback: the coverage metadata links back to the CNIG MDT05 bulk
  download page. Use this if the OGC coverage endpoint is unreliable for tiled
  requests.

Important service note, checked on 2026-07-07: small `coverage?f=COG&bbox=...`
requests to `api-coverages.idee.es` returned HTTP 500, while whole-coverage
requests returned the expected "request too large" error. Treat the API call
shape as unvalidated until a working subset request is found.

Expected code impact:

- Replace `highliner/repositories/dtm.py`'s ICGC-specific ArcGrid WCS client
  with an IGN MDT05 source, probably COG/subset based or local pre-tiled.
- Replace global `config.UTM_CRS` with a per-region CRS stored in `grid.json`
  and threaded through DTM fetch, bbox parsing, serializers, and `core/geo.py`.
- Confirm nodata semantics for IGN MDT05. Do not reuse ICGC's `SEA_SENTINEL`
  assumption without testing a coastal tile.

## Optional restrictions source

National protected-area source: MITECO Banco de Datos de la Naturaleza.

- ENP page:
  `https://www.miteco.gob.es/es/biodiversidad/servicios/banco-datos-naturaleza/informacion-disponible/enp.html`
- ENP dataset/catalog:
  `https://datos.gob.es/es/catalogo/e0dat0002-espacios-naturales-protegidos-enp_es`
- WMS:
  `https://wms.mapama.gob.es/sig/Biodiversidad/ENP/wms.aspx?Request=GetCapabilities`
- Download ZIP listed by datos.gob.es:
  `https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/gml_enp_es_tcm30-376404.zip`

This should replace, not extend, the Catalonia-specific layer derivation in
`highliner/repositories/restrictions.py`. The national ENP schema and labels
will not match the current `pein` / `parcs` / `fauna` assumptions.

## Region bboxes

Source for boundaries: IGN OGC API Features administrative units, filtered by
`nationallevel=https://inspire.ec.europa.eu/codelist/AdministrativeHierarchyLevel/2ndOrder`.

API:
`https://api-features.ign.es/collections/administrativeunit/items`

The bboxes below are rounded outward to the nearest 1000 m. Catalunya is omitted
because it is the existing region. "Territorios no asociados a ninguna
autonomía" is omitted.

| Region id | Name | NUTS | CRS | CLI bbox | 10 km chunks |
| --- | --- | --- | --- | --- | ---: |
| `andalucia` | Andalucía | ES61 | EPSG:25830 | `100000,3977000,622000,4289000` | 1696 |
| `aragon` | Aragón | ES24 | EPSG:25830 | `569000,4412000,811000,4755000` | 875 |
| `asturias` | Principado de Asturias | ES12 | EPSG:25830 | `161000,4754000,378000,4839000` | 198 |
| `canarias` | Canarias | ES70 | EPSG:4083 | `188000,3060000,662000,3256000` | 960 |
| `cantabria` | Cantabria | ES13 | EPSG:25830 | `349000,4734000,488000,4819000` | 126 |
| `castilla_la_mancha` | Castilla-La Mancha | ES42 | EPSG:25830 | `294000,4208000,682000,4576000` | 1443 |
| `castilla_y_leon` | Castilla y León | ES41 | EPSG:25830 | `165000,4439000,602000,4790000` | 1584 |
| `ceuta` | Ciudad Autónoma de Ceuta | ES63 | EPSG:25830 | `285000,3972000,295000,3978000` | 1 |
| `comunitat_valenciana` | Comunitat Valenciana | ES52 | EPSG:25830 | `626000,4190000,816000,4520000` | 627 |
| `extremadura` | Extremadura | ES43 | EPSG:25830 | `110000,4204000,358000,4487000` | 725 |
| `galicia` | Galicia | ES11 | EPSG:25830 | `-15000,4637000,193000,4860000` | 483 |
| `illes_balears` | Illes Balears | ES53 | EPSG:25830 | `860000,4286000,1127000,4463000` | 486 |
| `la_rioja` | La Rioja | ES23 | EPSG:25830 | `488000,4641000,610000,4722000` | 117 |
| `madrid` | Comunidad de Madrid | ES30 | EPSG:25830 | `365000,4415000,496000,4558000` | 210 |
| `melilla` | Ciudad Autónoma de Melilla | ES64 | EPSG:25830 | `502000,3902000,507000,3909000` | 1 |
| `murcia` | Región de Murcia | ES62 | EPSG:25830 | `557000,4137000,708000,4292000` | 256 |
| `navarra` | Comunidad Foral de Navarra | ES22 | EPSG:25830 | `540000,4640000,686000,4797000` | 240 |
| `pais_vasco` | País Vasco/Euskadi | ES21 | EPSG:25830 | `463000,4702000,604000,4812000` | 165 |

Total at the default 10 km chunk size: 10,193 chunks.

## Commands after source/CRS support exists

```sh
.venv/bin/highliner precompute --region andalucia --bbox 100000,3977000,622000,4289000
.venv/bin/highliner precompute --region aragon --bbox 569000,4412000,811000,4755000
.venv/bin/highliner precompute --region asturias --bbox 161000,4754000,378000,4839000
.venv/bin/highliner precompute --region canarias --bbox 188000,3060000,662000,3256000
.venv/bin/highliner precompute --region cantabria --bbox 349000,4734000,488000,4819000
.venv/bin/highliner precompute --region castilla_la_mancha --bbox 294000,4208000,682000,4576000
.venv/bin/highliner precompute --region castilla_y_leon --bbox 165000,4439000,602000,4790000
.venv/bin/highliner precompute --region ceuta --bbox 285000,3972000,295000,3978000
.venv/bin/highliner precompute --region comunitat_valenciana --bbox 626000,4190000,816000,4520000
.venv/bin/highliner precompute --region extremadura --bbox 110000,4204000,358000,4487000
.venv/bin/highliner precompute --region galicia --bbox -15000,4637000,193000,4860000
.venv/bin/highliner precompute --region illes_balears --bbox 860000,4286000,1127000,4463000
.venv/bin/highliner precompute --region la_rioja --bbox 488000,4641000,610000,4722000
.venv/bin/highliner precompute --region madrid --bbox 365000,4415000,496000,4558000
.venv/bin/highliner precompute --region melilla --bbox 502000,3902000,507000,3909000
.venv/bin/highliner precompute --region murcia --bbox 557000,4137000,708000,4292000
.venv/bin/highliner precompute --region navarra --bbox 540000,4640000,686000,4797000
.venv/bin/highliner precompute --region pais_vasco --bbox 463000,4702000,604000,4812000
```
