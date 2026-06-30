import json
from pathlib import Path
from highliner.router import deps


def test_is_chunked_layout(tmp_path: Path) -> None:
    (tmp_path / "catalonia").mkdir()
    (tmp_path / "catalonia" / "grid.json").write_text(json.dumps(
        {"bbox": [0, 0, 1, 1], "chunk_m": 10000.0}))
    (tmp_path / "classic").mkdir()
    assert deps.is_chunked_layout(tmp_path, "catalonia") is True
    assert deps.is_chunked_layout(tmp_path, "classic") is False
    assert deps.is_chunked_layout(tmp_path, "missing") is False
