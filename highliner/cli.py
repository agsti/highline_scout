import argparse
import time
from pathlib import Path
from highliner.core import config


def _fmt_hms(seconds: float) -> str:
    """Format a duration as H:MM:SS."""
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _cmd_ingest(args: argparse.Namespace) -> None:
    from highliner.repositories.dtm import fetch_dtm
    minx, miny, maxx, maxy = (float(v) for v in args.bbox.split(","))
    path = fetch_dtm((minx, miny, maxx, maxy), region=args.region,
                     data_dir=Path(args.data_dir))
    print(f"fetched DTM mosaic -> {path}")


def _cmd_analyze(args: argparse.Namespace) -> None:
    from highliner.models.raster import Raster
    from highliner.services.terrain import extract_anchors
    from highliner.repositories.anchors import save_anchors
    rdir = Path(args.data_dir) / args.region
    raster = Raster.open(rdir / "mosaic.tif")
    anchors = extract_anchors(
        raster, slope_min=config.SLOPE_MIN_DEG, radius=config.DROP_RADIUS_M,
        n_azimuths=config.N_AZIMUTHS, min_sector_drop=config.MIN_SECTOR_DROP_M,
        thin_dist=config.THIN_DIST_M)
    out = rdir / "anchors.parquet"
    save_anchors(anchors, out)
    print(f"extracted {len(anchors)} anchors -> {out}")


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    from highliner.app import create_app
    app = create_app(data_dir=Path(args.data_dir))
    uvicorn.run(app, host=args.host, port=args.port)


def _cmd_precompute(args: argparse.Namespace) -> None:
    from highliner.services import precompute as precompute_service
    minx, miny, maxx, maxy = (float(v) for v in args.bbox.split(","))
    bbox = (minx, miny, maxx, maxy)
    chunk_m = args.chunk_km * 1000.0

    start = time.monotonic()

    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - start
        pct = 100.0 * done / total if total else 100.0
        eta = elapsed / done * (total - done) if done else 0.0
        print(f"\rchunk {done}/{total} ({pct:4.1f}%)  "
              f"elapsed {_fmt_hms(elapsed)}  eta {_fmt_hms(eta)}",
              end="", flush=True)
    n = precompute_service.precompute(args.region, bbox, Path(args.data_dir),
                                      chunk_m=chunk_m, report=report)
    print(f"\nprocessed {n} chunks -> {Path(args.data_dir) / args.region}")


def _cmd_precompute_density(args: argparse.Namespace) -> None:
    from highliner.services import density
    region_dir = Path(args.data_dir) / args.region
    start = time.monotonic()

    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - start
        pct = 100.0 * done / total if total else 100.0
        print(f"\rpairs file {done}/{total} ({pct:4.1f}%)  "
              f"elapsed {_fmt_hms(elapsed)}", end="", flush=True)
    n = density.build_density(region_dir, report=report)
    print(f"\nwrote {n} density cells -> {region_dir / 'density'}")


def _cmd_fetch_restrictions(args: argparse.Namespace) -> None:
    from highliner.repositories.restrictions import fetch_all
    print("Downloading protected-area layers from the Generalitat WFS...")
    fetch_all()


def main(argv: list[str] | None = None) -> None:
    # Shared options available on every subcommand (e.g. after the verb).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", default=str(config.DATA_DIR))

    p = argparse.ArgumentParser(prog="highliner")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", parents=[common])
    pi.add_argument("--bbox", required=True, help="minx,miny,maxx,maxy EPSG:25831")
    pi.add_argument("--region", required=True)
    pi.set_defaults(func=_cmd_ingest)

    pa = sub.add_parser("analyze", parents=[common])
    pa.add_argument("--region", required=True)
    pa.set_defaults(func=_cmd_analyze)

    ps = sub.add_parser("serve", parents=[common])
    ps.add_argument("--host", default="127.0.0.1")
    ps.add_argument("--port", type=int, default=8000)
    ps.set_defaults(func=_cmd_serve)

    pc = sub.add_parser("precompute", parents=[common])
    pc.add_argument("--region", required=True)
    pc.add_argument("--bbox", required=True,
                    help="minx,miny,maxx,maxy in the region's CRS")
    pc.add_argument("--chunk-km", type=float, default=10.0)
    pc.set_defaults(func=_cmd_precompute)

    pd = sub.add_parser("precompute-density", parents=[common])
    pd.add_argument("--region", required=True)
    pd.set_defaults(func=_cmd_precompute_density)

    pr = sub.add_parser("fetch-restrictions", parents=[common])
    pr.set_defaults(func=_cmd_fetch_restrictions)

    args = p.parse_args(argv)
    args.func(args)
