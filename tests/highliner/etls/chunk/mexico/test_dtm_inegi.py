from pathlib import Path
from typing import Any

from highliner.etls.chunk.mexico import dtm_inegi


def test_sheet_keys_for_bbox_selects_catalogue_centres_inside_expanded_bbox() -> None:
    catalogue = [
        {"cve": "OUTSIDE", "x": 0, "y": 0},
        {"cve": "INSIDE", "x": -11000000, "y": 2200000},
    ]

    assert dtm_inegi._sheet_keys_for_bbox(
        catalogue, (-11001000, 2199000, -10999000, 2201000), "EPSG:3857") == [
            "INSIDE"]


def test_archive_url_uses_latest_terrain_ascii_record() -> None:
    records = [
        {"url_descarga": "https://example.test/new", "archivo": "_as.zip, 1 MB"},
        {"url_descarga": "https://example.test/old", "archivo": "_as.zip, 1 MB"},
    ]

    assert dtm_inegi._archive_url(records) == "https://example.test/new_as.zip"


def test_fetch_reuses_cached_extracted_sheet(
        tmp_path: Path, monkeypatch: Any) -> None:
    cache_dir = tmp_path / "cache"
    cached = cache_dir / "inegi_mdt5" / "F13D19A1.tif"
    cached.parent.mkdir(parents=True)
    cached.write_text("ncols 1\nnrows 1\nNODATA_value -9999\n0\n")
    monkeypatch.setattr(dtm_inegi, "_catalogue", lambda: [
        {"cve": "F13D19A1", "x": -11000000, "y": 2200000}])
    monkeypatch.setattr(dtm_inegi, "_sheet_keys_for_bbox",
                        lambda _catalogue, _bbox, _crs: ["F13D19A1"])
    monkeypatch.setattr(dtm_inegi, "_reproject", lambda source, dest, _crs: dest)

    paths = dtm_inegi.fetch(
        (-11001000, 2199000, -10999000, 2201000), tmp_path / "tiles",
        cache_dir, "EPSG:3857")

    assert paths == [tmp_path / "tiles" / "F13D19A1.tif"]
