import argparse
import time
from pathlib import Path
from highliner.core import config
from highliner.core.regions import defaults_for_region


def _fmt_hms(seconds: float) -> str:
    """Format a duration as H:MM:SS."""
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


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
    defaults = defaults_for_region(args.region)
    crs = args.crs or defaults.crs
    dtm_source = args.dtm_source or defaults.dtm_source

    start = time.monotonic()

    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - start
        pct = 100.0 * done / total if total else 100.0
        eta = elapsed / done * (total - done) if done else 0.0
        print(f"\rchunk {done}/{total} ({pct:4.1f}%)  "
              f"elapsed {_fmt_hms(elapsed)}  eta {_fmt_hms(eta)}",
              end="", flush=True)
    n = precompute_service.precompute(args.region, bbox, Path(args.data_dir),
                                      chunk_m=chunk_m, report=report,
                                      crs=crs, dtm_source=dtm_source,
                                      workers=args.workers)
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

    ps = sub.add_parser("serve", parents=[common])
    ps.add_argument("--host", default="127.0.0.1")
    ps.add_argument("--port", type=int, default=8000)
    ps.set_defaults(func=_cmd_serve)

    pc = sub.add_parser("precompute", parents=[common])
    pc.add_argument("--region", required=True)
    pc.add_argument("--bbox", required=True,
                    help="minx,miny,maxx,maxy in the region's CRS")
    pc.add_argument("--chunk-km", type=float, default=10.0)
    pc.add_argument("--crs", help="projected CRS for bbox and stored data")
    pc.add_argument("--dtm-source", choices=["icgc", "idee", "cnig"],
                    help="terrain source; defaults from the region name")
    pc.add_argument("--workers", type=int, default=1,
                    help="number of chunks to precompute concurrently")
    pc.set_defaults(func=_cmd_precompute)

    pd = sub.add_parser("precompute-density", parents=[common])
    pd.add_argument("--region", required=True)
    pd.set_defaults(func=_cmd_precompute_density)

    pr = sub.add_parser("fetch-restrictions", parents=[common])
    pr.set_defaults(func=_cmd_fetch_restrictions)

    args = p.parse_args(argv)
    args.func(args)
