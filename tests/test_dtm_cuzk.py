import io
import zipfile
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import box

from highliner.etls.chunk import dtm, dtm_cuzk


def test_parse_catalog_keeps_both_parts_of_cuzk_sheet_id() -> None:
    catalog = b'''<feed xmlns="http://www.w3.org/2005/Atom"
        xmlns:georss="http://www.georss.org/georss"><entry>
        <id>https://atom.cuzk.gov.cz/feed/CZ_DMR4G-ETRS89-TIFF_302_5550.xml</id>
        <georss:polygon>50.0 12.0 50.0 12.1 50.1 12.1 50.1 12.0</georss:polygon>
        </entry></feed>'''

    assert dtm_cuzk._parse_catalog(catalog) == [{
        "id": "302_5550", "bbox": [12.0, 50.0, 12.1, 50.1],
    }]


def test_parse_catalog_ignores_incomplete_entries_and_rejects_empty_catalog() -> None:
    catalog = b'''<feed xmlns="http://www.w3.org/2005/Atom"
        xmlns:georss="http://www.georss.org/georss">
        <entry><id>missing-polygon.xml</id></entry>
        <entry><georss:polygon>50 12 50 13 51 13</georss:polygon></entry>
        </feed>'''

    with pytest.raises(RuntimeError, match="contained no DMR 4G tiles"):
        dtm_cuzk._parse_catalog(catalog)


def test_cuzk_client_rejects_non_native_crs_without_touching_cache(
        tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="only in EPSG:3045"):
        dtm_cuzk.fetch_cuzk_dmr4g((1, 2, 3, 4), tmp_path, "EPSG:4326")
    assert not (tmp_path / "dmr4g").exists()


def test_cuzk_cached_catalog_and_sheet_are_reused_without_network(
        tmp_path: Path) -> None:
    root = tmp_path / "dmr4g"
    root.mkdir()
    (root / "atom_index.json").write_text(
        '[{"id": "302_5550", "bbox": [12.0, 50.0, 12.1, 50.1]}]')
    sheet = root / "302_5550.tif"
    sheet.write_bytes(b"cached terrain")
    x, y = Transformer.from_crs(
        "EPSG:4326", "EPSG:3045", always_xy=True).transform(12.05, 50.05)

    paths = dtm_cuzk.fetch_cuzk_dmr4g(
        (x - 100, y - 100, x + 100, y + 100), tmp_path, "EPSG:3045")

    assert paths == [sheet]


def test_fetch_tiles_dispatches_cuzk_dmr4g_to_cached_client(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_fetch(bbox: dtm.Bbox, cache_dir: Path, crs: str) -> list[Path]:
        seen.update(bbox=bbox, cache_dir=cache_dir, crs=crs)
        return [cache_dir / "dmr4g" / "302_5550.tif"]

    monkeypatch.setattr(dtm_cuzk, "fetch_cuzk_dmr4g", fake_fetch)

    paths = dtm.fetch_tiles(
        (285000, 5380000, 287000, 5382000), tmp_path / "tiles",
        source="cuzk_dmr4g", crs="EPSG:3045", cache_dir=tmp_path / "cache")

    assert paths == [tmp_path / "cache" / "dmr4g" / "302_5550.tif"]
    assert seen == {
        "bbox": (285000, 5380000, 287000, 5382000),
        "cache_dir": tmp_path / "cache",
        "crs": "EPSG:3045",
    }


def test_cuzk_client_extracts_world_file_with_geotiff(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("302_5550.tif", b"tiff")
        archive.writestr("302_5550.tfw", b"5\n0\n0\n-5\n302002.5\n5551997.5\n")

    class Response:
        content = bundle.getvalue()

    monkeypatch.setattr(dtm_cuzk, "_load_index", lambda _root: [{
        "id": "302_5550", "bbox": [12.0, 50.0, 12.1, 50.1],
    }])
    monkeypatch.setattr(dtm_cuzk, "_bbox_lonlat",
                        lambda _bbox: box(12.0, 50.0, 12.1, 50.1))
    monkeypatch.setattr(dtm_cuzk, "_get", lambda _url: Response())

    paths = dtm_cuzk.fetch_cuzk_dmr4g((1, 2, 3, 4), tmp_path, "EPSG:3045")

    assert paths == [tmp_path / "dmr4g" / "302_5550.tif"]
    assert paths[0].with_suffix(".tfw").read_text().startswith("5\n")
