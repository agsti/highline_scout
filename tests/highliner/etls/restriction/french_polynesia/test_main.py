import json
from pathlib import Path

from highliner.etls.restriction.french_polynesia import main as polynesia


def test_polynesia_restrictions_keep_only_the_national_territory(
        tmp_path: Path) -> None:
    source = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"nom_site": "Moorea",
             "territoire": "PYF"},
             "geometry": {"type": "Point", "coordinates": [-149.8, -17.5]}},
            {"type": "Feature", "properties": {"nom_site": "France",
             "territoire": "METROP"},
             "geometry": {"type": "Point", "coordinates": [2.0, 46.0]}},
        ],
    }
    (tmp_path / "protected.geojson").write_text(json.dumps(source))

    result = polynesia._load_source("protected", tmp_path)

    assert result["nom_site"].tolist() == ["Moorea"]


def test_polynesia_restrictions_are_registered_for_density() -> None:
    from highliner.core.density import layer_mask
    from highliner.core.restrictions import LAYERS

    assert layer_mask(["pf_protected"]) != 0
    assert "pf_protected" in LAYERS
