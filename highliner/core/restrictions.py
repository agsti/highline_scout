"""Registry of protected-area overlay layers, shared by both stages.

The specification of each derived layer (its display metadata plus the
predicate that selects its features from a source) lives here because both
sides need it: the ETL build (``highliner.etls.repositories.restrictions``) is
driven by it, and the serving helpers
(``highliner.server.services.restrictions``) expose its display metadata to the
frontend. Keeping it here avoids a cross-stage import between etl and server.
"""
from collections.abc import Callable, Mapping
from typing import Any, TypedDict

ZEPA_VALUES = frozenset({"SpecialProtectionArea", "SpecialProtecionArea"})
ZEC_VALUES = frozenset({"SpecialAreaOfConservation", "SiteOfCommunityImportance"})


class LayerSpec(TypedDict):
    label: str
    color: str
    source: str
    name_field: str
    keep: Callable[[Mapping[str, Any]], bool]
    tooltip: str
    highlight: str


# Derived overlay layers. Each pulls from a loaded source and optionally
# filters by a predicate on properties, and renames one field to `name`.
LAYERS: dict[str, LayerSpec] = {
    "zepa": {
        "label": "ZEPA (Birds)",
        "color": "#e31a1c",
        "source": "rn2000",
        "name_field": "text",
        "keep": lambda p: bool(ZEPA_VALUES & set(p.get("designations") or ())),
        "tooltip": ("Special Protection Area for Birds - Red Natura 2000 (EU "
                    "Birds Directive). Cliffs in these areas commonly have "
                    "seasonal climbing and access closures for raptor nesting "
                    "(roughly winter to summer, varies by site); check with the "
                    "managing body before rigging."),
        "highlight": ("Cliffs in these areas commonly have seasonal climbing and "
                      "access closures for raptor nesting (roughly winter to "
                      "summer, varies by site); check with the managing body "
                      "before rigging."),
    },
    "zec": {
        "label": "ZEC / LIC",
        "color": "#ff7f00",
        "source": "rn2000",
        "name_field": "text",
        "keep": lambda p: bool(ZEC_VALUES & set(p.get("designations") or ())),
        "tooltip": ("Site of Community Importance / Special Area of Conservation "
                    "- Red Natura 2000 (EU Habitats Directive). Activities that "
                    "may harm the protected habitats can be regulated and may "
                    "require an environmental impact assessment."),
        "highlight": ("Activities that may harm the protected habitats can be "
                      "regulated and may require an environmental impact "
                      "assessment."),
    },
    "enp": {
        "label": "Protected Natural Areas",
        "color": "#6a3d9a",
        "source": "enp",
        "name_field": "SITE_NAME",
        "keep": lambda p: True,
        "tooltip": ("Protected Natural Area - a national or regional protection "
                    "figure such as a national or nature park, nature reserve or "
                    "natural monument, each with its own management plan. "
                    "Climbing, bivouacking, drones and organized events are often "
                    "regulated and may need authorization from the managing "
                    "body."),
        "highlight": ("Climbing, bivouacking, drones and organized events are "
                      "often regulated and may need authorization from the "
                      "managing body."),
    },
}
