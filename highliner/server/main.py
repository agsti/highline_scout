import argparse
from pathlib import Path

import uvicorn

from highliner.core import config
from highliner.server.app import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-server")
    parser.add_argument("--data-dir", default=str(config.DATA_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    app = create_app(data_dir=Path(args.data_dir))
    uvicorn.run(app, host=args.host, port=args.port)
