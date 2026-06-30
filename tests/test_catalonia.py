from pathlib import Path
import pytest
from highliner.services import catalonia


def test_chunk_grid_tiles_bbox() -> None:
    bbox = (0.0, 0.0, 25000.0, 15000.0)        # 25 x 15 km, 10 km chunks
    chunks = list(catalonia.chunk_grid(bbox, chunk_m=10000.0))
    assert len(chunks) == 3 * 2                 # 3 cols x 2 rows
    assert len({(cx, cy) for cx, cy, _ in chunks}) == 6
    for cx, cy, (x0, y0, x1, y1) in chunks:
        assert x1 <= 25000.0 and y1 <= 15000.0
        assert x1 > x0 and y1 > y0
    top_right = [c for c in chunks if c[0] == 2 and c[1] == 1][0]
    assert top_right[2] == (20000.0, 10000.0, 25000.0, 15000.0)   # clipped remainder
