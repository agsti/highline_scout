from pathlib import Path

import pytest

from highliner.server import main as server_main


def test_server_command_starts_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_create_app(data_dir: Path) -> object:
        calls["data_dir"] = data_dir
        return object()

    def fake_run(app: object, host: str, port: int) -> None:
        calls.update(app=app, host=host, port=port)

    monkeypatch.setattr("highliner.server.main.create_app", fake_create_app)
    monkeypatch.setattr("highliner.server.main.uvicorn.run", fake_run)
    server_main.main(["--data-dir", "/tmp/x", "--host", "0.0.0.0",
                      "--port", "9000"])
    assert calls["data_dir"] == Path("/tmp/x")
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 9000
