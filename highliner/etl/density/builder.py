"""Offline builder for the zoomed-out density pyramid."""
import json
from collections.abc import Callable, Iterable
from pathlib import Path

from highliner.core import config, geo, tiles
from highliner.core.regions import defaults_for_region
from highliner.etl.density.candidates import load_candidates
from highliner.etl.density.histogram import bucket_for
from highliner.etl.density.restrictions import candidate_mask, load_layers
from highliner.models.candidate import Candidate
from highliner.server.repositories import chunked_store


def _midpoint_lonlat(c: Candidate, crs: str) -> tuple[float, float]:
    mx = (c.a.x + c.b.x) / 2.0
    my = (c.a.y + c.b.y) / 2.0
    return geo.to_lonlat_crs(mx, my, crs)


def build_density(region_dir: Path,
                  zoom_levels: Iterable[int] = config.DENSITY_ZOOM_LEVELS,
                  report: Callable[[int, int], None] | None = None,
                  country: str = config.DEFAULT_COUNTRY,
                  data_dir: Path | str = config.DATA_DIR) -> int:
    """Build ``region_dir/density/z{z}.json`` for each zoom. Returns the total
    number of cells written across all zoom levels."""
    region_dir = Path(region_dir)
    try:
        crs = chunked_store.read_grid(region_dir).crs
    except FileNotFoundError:
        crs = defaults_for_region(region_dir.name).crs
    zooms = list(zoom_levels)
    pair_files = sorted((region_dir / "pairs").glob("q_*.parquet"))
    layers = load_layers(Path(data_dir) / country / "restrictions", crs)

    # (z, xtile, ytile) -> [count, max_exposure, min_length, max_length]
    cells: dict[tuple[int, int, int], list[float]] = {}
    histograms: dict[tuple[int, int, int, int, int, int], int] = {}
    total = len(pair_files)
    for done, path in enumerate(pair_files, start=1):
        for c in load_candidates(path):
            lon, lat = _midpoint_lonlat(c, crs)
            mask = candidate_mask(c, layers)
            for z in zooms:
                tx, ty = tiles.lonlat_to_tile(lon, lat, z)
                key = (z, tx, ty)
                hist_key = (*key, bucket_for(c.length), bucket_for(c.exposure),
                            mask)
                histograms[hist_key] = histograms.get(hist_key, 0) + 1
                cell = cells.get(key)
                if cell is None:
                    cells[key] = [1.0, c.exposure, c.length, c.length]
                else:
                    cell[0] += 1.0
                    cell[1] = max(cell[1], c.exposure)
                    cell[2] = min(cell[2], c.length)
                    cell[3] = max(cell[3], c.length)
        if report is not None:
            report(done, total)

    out_dir = region_dir / "density"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for z in zooms:
        rows = []
        for (zz, tx, ty), (n, max_exp, min_len, max_len) in cells.items():
            if zz != z:
                continue
            hist = [[length_bucket, exposure_bucket, mask, count]
                    for (z_hist, x_hist, y_hist, length_bucket,
                         exposure_bucket, mask), count in sorted(histograms.items())
                    if (z_hist, x_hist, y_hist) == (zz, tx, ty)]
            rows.append({"x": tx, "y": ty, "n": int(n), "max_exp": max_exp,
                         "min_len": min_len, "max_len": max_len, "hist": hist})
        (out_dir / f"z{z}.json").write_text(json.dumps(rows))
        written += len(rows)
    return written
