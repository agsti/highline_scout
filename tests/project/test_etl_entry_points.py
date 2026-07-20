"""Every country ETL CLI stays reachable as `python -m <module>`.

This is a refactor guard: the module path is the public contract used by the
justfile and AGENTS.md, and it must survive the move to country packages.
"""
import subprocess
import sys

import pytest

CHUNK_COUNTRIES = ("austria", "czechia", "france", "italy", "poland", "spain",
                   "switzerland", "united_kingdom")
DENSITY_COUNTRIES = CHUNK_COUNTRIES
RESTRICTION_COUNTRIES = tuple(c for c in CHUNK_COUNTRIES
                              if c != "united_kingdom")

CASES = ([("chunk", c) for c in CHUNK_COUNTRIES]
         + [("density", c) for c in DENSITY_COUNTRIES]
         + [("restriction", c) for c in RESTRICTION_COUNTRIES])


@pytest.mark.parametrize(("stage", "country"), CASES,
                         ids=[f"{s}-{c}" for s, c in CASES])
def test_country_cli_is_runnable_as_module(stage: str, country: str) -> None:
    module = f"highliner.etls.{stage}.{country}"
    result = subprocess.run([sys.executable, "-m", module, "--help"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, (
        f"{module} --help exited {result.returncode}\n{result.stderr}")
    assert "usage:" in result.stdout
