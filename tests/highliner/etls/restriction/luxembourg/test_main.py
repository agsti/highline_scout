import io
import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.luxembourg import main as luxembourg

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


@pytest.mark.parametrize("layer", ["zepa", "zec", "enp"])
def test_luxembourg_restriction_specs_keep_features(layer: str) -> None:
    name_field = luxembourg.SPECS[layer].name_field
    source = gpd.GeoDataFrame({name_field: ["  Reserve  "]},
                              geometry=[_SQUARE], crs="EPSG:4326")
    built = shared.build_layer(source, luxembourg.SPECS[layer])
    assert list(built["name"]) == ["Reserve"]


def test_luxembourg_main_downloads_then_writes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(luxembourg, "download_sources",
                        lambda raw_dir: calls.append(raw_dir))
    monkeypatch.setattr(luxembourg.shared, "write_layers", lambda *args: {})

    luxembourg.main(["--data-dir", str(tmp_path)])

    assert calls == [tmp_path / "luxembourg" / "restrictions" / "raw"]


def test_luxembourg_zpin_loader_assigns_declared_laea_crs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "zpin.gml"
    path.write_text("placeholder")
    source = gpd.GeoDataFrame(
        {"sitename0_geographicalname_spelling0_spellingofname_text": ["ZPIN"]},
        geometry=[Polygon([(4_000_000, 3_000_000), (4_000_001, 3_000_000),
                          (4_000_001, 3_000_001), (4_000_000, 3_000_001)])],
    )
    monkeypatch.setattr(gpd, "read_file", lambda _: source.copy())
    loaded = luxembourg._load_source("enp", tmp_path)
    assert loaded.crs.to_epsg() == 4326


class _Response:
    """Minimal stand-in for a streamed ``requests`` response."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, _size: int) -> list[bytes]:
        return [self._body, b""]


def _zipped(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_luxembourg_download_sources_unpacks_archives_and_keeps_the_gml(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bodies = {
        luxembourg.SOURCE_URLS["zepa"]: _zipped(
            {"nested/LUDO_20250613.shp": b"zepa-shape"}),
        luxembourg.SOURCE_URLS["zec"]: _zipped(
            {"LUDH_20250613.shp": b"zec-shape"}),
        luxembourg.SOURCE_URLS["enp"]: b"<gml/>",
    }
    monkeypatch.setattr(
        "highliner.etls.restriction.luxembourg.main.requests.get",
        lambda url, stream, timeout: _Response(bodies[url]))

    luxembourg.download_sources(tmp_path)

    assert (tmp_path / "LUDO_20250613.shp").read_bytes() == b"zepa-shape"
    assert (tmp_path / "LUDH_20250613.shp").read_bytes() == b"zec-shape"
    assert (tmp_path / "zpin.gml").read_bytes() == b"<gml/>"
    assert not list(tmp_path.glob("*.zip"))


def test_luxembourg_download_sources_skips_what_is_already_cached(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "LUDO_cached.shp").write_bytes(b"zepa")
    (tmp_path / "LUDH_cached.shp").write_bytes(b"zec")
    (tmp_path / "zpin.gml").write_bytes(b"<gml/>")
    monkeypatch.setattr(
        "highliner.etls.restriction.luxembourg.main.requests.get",
        lambda *args, **kwargs: pytest.fail("re-downloaded"))

    luxembourg.download_sources(tmp_path)

    assert (tmp_path / "LUDO_cached.shp").read_bytes() == b"zepa"


def test_luxembourg_loader_rejects_an_unknown_layer(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        luxembourg._load_source("national_park", tmp_path)


def test_luxembourg_loader_reports_a_missing_source_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no zepa source"):
        luxembourg._load_source("zepa", tmp_path)


def test_luxembourg_loader_refuses_a_shapefile_without_a_crs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "LUDO_20250613.shp").write_text("placeholder")
    source = gpd.GeoDataFrame({"SITENAME": ["Reserve"]}, geometry=[_SQUARE])
    monkeypatch.setattr(gpd, "read_file", lambda _: source.copy())

    with pytest.raises(ValueError, match="has no CRS"):
        luxembourg._load_source("zepa", tmp_path)


def test_luxembourg_loader_reprojects_a_georeferenced_shapefile(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "LUDH_20250613.shp").write_text("placeholder")
    source = gpd.GeoDataFrame(
        {"SITENAME": ["Habitat"]},
        geometry=[Polygon([(75_000, 75_000), (75_100, 75_000),
                           (75_100, 75_100), (75_000, 75_100)])],
        crs="EPSG:2169")
    monkeypatch.setattr(gpd, "read_file", lambda _: source.copy())

    loaded = luxembourg._load_source("zec", tmp_path)

    assert loaded.crs.to_epsg() == 4326
    assert list(loaded["SITENAME"]) == ["Habitat"]
