# Split Command Mains Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mixed `highliner` dispatcher with independently packaged
server, chunk-precompute, density, and restrictions commands.

**Architecture:** Each new `main.py` owns parsing, output, and command-local
helpers for one execution concern. It calls the existing application, service,
or repository boundary directly, so no CLI dispatch or handler layer remains.

**Tech Stack:** Python 3.11+, argparse, Uvicorn, pytest, setuptools, uv/Just.

## Global Constraints

- Preserve the existing service APIs, output data layout, and FastAPI routes.
- Every command exports `main(argv: list[str] | None = None) -> None`.
- Keep CLI-only helpers within the command module that uses them.
- Remove `highliner/cli.py` and the legacy `highliner` script.
- Satisfy 88-column formatting, strict mypy, Ruff, Vulture, and the file cap.

---

## File Structure

- Create `highliner/server/main.py`: server parser and Uvicorn startup.
- Create `highliner/etl/chunk/__init__.py` and `main.py`: chunk precompute.
- Create `highliner/etl/density/main.py`: density precompute.
- Create `highliner/restrictions/__init__.py` and `main.py`: layer builds.
- Delete `highliner/cli.py`; update `pyproject.toml`, `justfile`,
  `README.md`, `AGENTS.md`, and `tests/test_cli.py`.

### Task 1: Add the server command

**Files:**
- Create: `highliner/server/main.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `create_app(data_dir: Path | None = None) -> FastAPI`.
- Produces: `highliner.server.main.main(argv: list[str] | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

```python
from highliner.server import main as server_main


def test_server_command_starts_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(server_main, "create_app",
                        lambda data_dir: calls.setdefault("data_dir", data_dir))
    monkeypatch.setattr(server_main.uvicorn, "run",
                        lambda app, host, port: calls.update(
                            app=app, host=host, port=port))
    server_main.main(["--data-dir", "/tmp/x", "--host", "0.0.0.0",
                      "--port", "9000"])
    assert calls["data_dir"] == Path("/tmp/x")
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 9000
```

- [ ] **Step 2: Run it red**

Run: `uv run pytest tests/test_cli.py::test_server_command_starts_uvicorn -v`

Expected: FAIL because `highliner.server.main` does not exist.

- [ ] **Step 3: Implement**

Create a parser with `prog="highliner-server"`, `--data-dir` defaulting to
`str(config.DATA_DIR)`, `--host` defaulting to `127.0.0.1`, and integer
`--port` defaulting to `8000`. Pass `Path(args.data_dir)` to
`create_app`, then call `uvicorn.run`.

- [ ] **Step 4: Verify green and commit**

Run: `uv run pytest tests/test_cli.py::test_server_command_starts_uvicorn -v`

Expected: PASS.

```bash
git add highliner/server/main.py tests/test_cli.py
git commit -m "feat(server): add dedicated server command"
```

### Task 2: Add the ETL commands

**Files:**
- Create: `highliner/etl/chunk/__init__.py`
- Create: `highliner/etl/chunk/main.py`
- Create: `highliner/etl/density/main.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: existing `etl.services.precompute.precompute` and
  `etl.services.density.build_density`.
- Produces: `highliner.etl.chunk.main.main(argv)` and
  `highliner.etl.density.main.main(argv)`.

- [ ] **Step 1: Write the failing tests**

```python
from highliner.etl.chunk import main as chunk_main
from highliner.etl.density import main as density_main


def test_chunk_command_uses_region_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(chunk_main.precompute_service, "precompute",
                        lambda region, bbox, data_dir, **kwargs:
                        calls.update(region=region, bbox=bbox, data_dir=data_dir,
                                     **kwargs) or 1)
    chunk_main.main(["--region", "catalonia", "--data-dir", "/tmp/x",
                     "--bbox", "0,0,10000,10000", "--workers", "4"])
    assert calls["chunk_m"] == 10000.0
    assert calls["crs"] == "EPSG:25831"
    assert calls["dtm_source"] == "icgc"
    assert calls["workers"] == 4


def test_density_command_uses_region_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(density_main.density, "build_density",
                        lambda region_dir, report: calls.setdefault(
                            "region_dir", region_dir) or 7)
    density_main.main(["--region", "catalonia", "--data-dir", "/tmp/x"])
    assert calls["region_dir"] == Path("/tmp/x/spain/catalonia")
```

- [ ] **Step 2: Run them red**

Run: `uv run pytest tests/test_cli.py -k 'chunk_command or density_command' -v`

Expected: FAIL because the focused modules do not exist.

- [ ] **Step 3: Implement**

Move the precompute parser, `_fmt_hms`, elapsed/ETA reporter, default CRS/DTM
resolution, and service call from `cli.py` into the chunk command. Its parser
uses `prog="highliner-etl-chunk"` and preserves every existing option:
`--data-dir`, `--region`, `--bbox`, `--chunk-km`, `--crs`,
`--dtm-source`, and `--workers`.

Put an independent `_fmt_hms`, density parser, elapsed reporter, and density
call in `highliner.etl.density.main`. Its parser uses
`prog="highliner-etl-density"` and accepts `--data-dir` and required
`--region`. Neither module imports CLI helpers from the other.

- [ ] **Step 4: Verify green and commit**

Run: `uv run pytest tests/test_cli.py -k 'chunk_command or density_command' -v`

Expected: PASS.

```bash
git add highliner/etl/chunk highliner/etl/density/main.py tests/test_cli.py
git commit -m "feat(etl): add focused precompute commands"
```

### Task 3: Add the restrictions command

**Files:**
- Create: `highliner/restrictions/__init__.py`
- Create: `highliner/restrictions/main.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `highliner.etl.repositories.restrictions.fetch_all() -> None`.
- Produces: `highliner.restrictions.main.main(argv: list[str] | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

```python
from highliner.restrictions import main as restrictions_main


def test_restrictions_command_builds_layers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(restrictions_main, "fetch_all",
                        lambda: calls.append("called"))
    restrictions_main.main([])
    assert calls == ["called"]
```

- [ ] **Step 2: Run it red**

Run: `uv run pytest tests/test_cli.py::test_restrictions_command_builds_layers -v`

Expected: FAIL because `highliner.restrictions.main` does not exist.

- [ ] **Step 3: Implement**

Create a parser with `prog="highliner-restrictions"`, retain the existing
protected-area status message, parse `argv`, and call `fetch_all()`.

- [ ] **Step 4: Verify green and commit**

Run: `uv run pytest tests/test_cli.py::test_restrictions_command_builds_layers -v`

Expected: PASS.

```bash
git add highliner/restrictions tests/test_cli.py
git commit -m "feat: add restrictions command"
```

### Task 4: Migrate package scripts and callers

**Files:**
- Delete: `highliner/cli.py`
- Modify: `pyproject.toml`, `justfile`, `README.md`, `AGENTS.md`,
  and `tests/test_cli.py`

**Interfaces:**
- Produces scripts `highliner-server`, `highliner-etl-chunk`,
  `highliner-etl-density`, and `highliner-restrictions`.

- [ ] **Step 1: Write the failing entry-point test**

```python
def test_project_defines_focused_command_scripts() -> None:
    project = Path("pyproject.toml").read_text()
    assert 'highliner-server = "highliner.server.main:main"' in project
    assert 'highliner-etl-chunk = "highliner.etl.chunk.main:main"' in project
    assert 'highliner-etl-density = "highliner.etl.density.main:main"' in project
    assert 'highliner-restrictions = "highliner.restrictions.main:main"' in project
    assert "highliner.cli:main" not in project
```

- [ ] **Step 2: Run it red**

Run: `uv run pytest tests/test_cli.py::test_project_defines_focused_command_scripts -v`

Expected: FAIL because `pyproject.toml` still defines the legacy script.

- [ ] **Step 3: Implement migration**

Replace `[project.scripts]` with the four exact entry points in the test.
Delete `highliner/cli.py`. Update Just recipes to call the replacement
commands; update the live command examples in `README.md` and `AGENTS.md`;
remove central-dispatch imports from CLI tests.

- [ ] **Step 4: Verify green and commit**

Run: `uv run pytest tests/test_cli.py -v`

Expected: PASS.

```bash
git add AGENTS.md README.md justfile pyproject.toml tests/test_cli.py
git rm highliner/cli.py
git commit -m "refactor: replace mixed highliner CLI"
```

### Task 5: Full verification

- [ ] **Step 1: Run all tests**

Run: `just test`

Expected: exit 0 with no test failures.

- [ ] **Step 2: Run static checks**

Run: `just lint && just typecheck && just deadcode`

Expected: all checks exit 0 with no findings.

- [ ] **Step 3: Smoke-test installed commands**

Run: `uv run highliner-server --help && uv run highliner-etl-chunk --help && uv run highliner-etl-density --help && uv run highliner-restrictions --help`

Expected: each command prints focused help and exits 0.

- [ ] **Step 4: Inspect final scope**

Run: `git diff --check main...HEAD && git status --short`

Expected: no whitespace errors and only intentional changes.

## Self-Review

- Spec coverage: Tasks 1–3 place each command in its requested module; Task 4
  removes the dispatcher and migrates every caller; Task 5 verifies the result.
- Placeholder scan: no unresolved decisions or TODO markers remain.
- Type consistency: all public command modules expose the same `main(argv)`
  signature and call existing service interfaces.
