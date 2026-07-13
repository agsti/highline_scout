import argparse

from highliner.etl.repositories.restrictions import fetch_all


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-restrictions")
    parser.parse_args(argv)
    print("Building national protected-area layers from "
          "data/spain/restrictions/raw/ ...")
    fetch_all()
