import argparse
from pathlib import Path
from highliner.core import config


def _cmd_ingest(args):
    from highliner.repositories.dtm import fetch_dtm
    bbox = tuple(float(v) for v in args.bbox.split(","))
    path = fetch_dtm(bbox, region=args.region, data_dir=Path(args.data_dir))
    print(f"fetched DTM mosaic -> {path}")


def _cmd_analyze(args):
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


def _cmd_serve(args):
    import uvicorn
    from highliner.app import create_app
    app = create_app(data_dir=Path(args.data_dir))
    uvicorn.run(app, host=args.host, port=args.port)


def _cmd_fetch_restrictions(args):
    from highliner.repositories.restrictions import fetch_all
    print("Downloading protected-area layers from the Generalitat WFS...")
    fetch_all()


def main(argv=None):
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

    pr = sub.add_parser("fetch-restrictions", parents=[common])
    pr.set_defaults(func=_cmd_fetch_restrictions)

    args = p.parse_args(argv)
    args.func(args)
