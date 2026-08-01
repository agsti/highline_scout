import json
from pathlib import Path

from highliner.etls.chunk.ireland import dtm_gsi


def test_fetch_gsi_uses_intersecting_catalog_archives(
        monkeypatch, tmp_path: Path) -> None:
    catalog = {
        "features": [{
            "attributes": {"DATA_NAME": "P_602766", "DATA_URL": "https://x/a.7z"},
            "geometry": {"rings": [[[500_000, 700_000], [510_000, 700_000],
                                      [510_000, 710_000], [500_000, 700_000]]]},
        }],
    }
    monkeypatch.setattr(dtm_gsi, "_catalog", lambda: catalog)
    seen: list[tuple[str, Path]] = []

    def materialize(url: str, name: str, root: Path) -> Path:
        seen.append((url, root))
        path = root / f"{name}.tif"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"tif")
        return path

    monkeypatch.setattr(dtm_gsi, "_materialize", materialize)
    paths = dtm_gsi.fetch_gsi_lidar((504_000, 704_000, 506_000, 706_000),
                                     tmp_path, "EPSG:2157")

    assert paths == [tmp_path / "gsi-lidar-1m" / "P_602766.tif"]
    assert seen == [("https://x/a.7z", tmp_path / "gsi-lidar-1m")]


def test_catalog_features_are_cached(monkeypatch, tmp_path: Path) -> None:
    payload = {"features": []}
    monkeypatch.setattr(dtm_gsi, "_download_catalog", lambda: payload)

    assert dtm_gsi._load_catalog(tmp_path) == payload
    assert json.loads((tmp_path / "catalog.json").read_text()) == payload

