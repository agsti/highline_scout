"""Display metadata for protected-area overlay layers served to the frontend."""
from typing import TypedDict


class LayerSpec(TypedDict):
    label: str
    color: str
    tooltip: str
    highlight: str


LAYERS: dict[str, LayerSpec] = {
    "zepa": {
        "label": "ZEPA (Birds)",
        "color": "#e31a1c",
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
    # Italy. Same semantics as the Spanish layers above (birds / habitats /
    # national protected areas), so they share those layers' colors — the two
    # countries never overlap on the map.
    "zps": {
        "label": "ZPS (Birds)",
        "color": "#e31a1c",
        "tooltip": ("Special Protection Area for Birds - Natura 2000 (EU Birds "
                    "Directive; Italian ZPS). Cliffs in these areas commonly "
                    "have seasonal climbing and access closures for raptor "
                    "nesting (roughly winter to summer, varies by site); check "
                    "with the managing body before rigging."),
        "highlight": ("Cliffs in these areas commonly have seasonal climbing and "
                      "access closures for raptor nesting (roughly winter to "
                      "summer, varies by site); check with the managing body "
                      "before rigging."),
    },
    "zsc": {
        "label": "ZSC / SIC",
        "color": "#ff7f00",
        "tooltip": ("Site of Community Importance / Special Area of Conservation "
                    "- Natura 2000 (EU Habitats Directive; Italian ZSC/SIC). "
                    "Activities that may harm the protected habitats can be "
                    "regulated and may require an environmental impact "
                    "assessment."),
        "highlight": ("Activities that may harm the protected habitats can be "
                      "regulated and may require an environmental impact "
                      "assessment."),
    },
    "euap": {
        "label": "Protected Areas (EUAP)",
        "color": "#6a3d9a",
        "tooltip": ("Officially listed protected natural area (Italian EUAP) - "
                    "a national or regional park, nature reserve or other "
                    "protection figure, each with its own rules and managing "
                    "body. Climbing, bivouacking, drones and organized events "
                    "are often regulated and may need authorization from the "
                    "managing body."),
        "highlight": ("Climbing, bivouacking, drones and organized events are "
                      "often regulated and may need authorization from the "
                      "managing body."),
    },
    # France. Same semantics as the Spanish and Italian layers above (birds /
    # habitats / national protected areas), so they share those layers'
    # colors — the countries never overlap on the map.
    "fr_zps": {
        "label": "ZPS (Birds)",
        "color": "#e31a1c",
        "tooltip": ("Special Protection Area for Birds - Natura 2000 (EU Birds "
                    "Directive; French ZPS). Cliffs in these areas commonly "
                    "have seasonal climbing and access closures for raptor "
                    "nesting (roughly winter to summer, varies by site); check "
                    "with the managing body before rigging."),
        "highlight": ("Cliffs in these areas commonly have seasonal climbing and "
                      "access closures for raptor nesting (roughly winter to "
                      "summer, varies by site); check with the managing body "
                      "before rigging."),
    },
    "fr_zsc": {
        "label": "ZSC / SIC",
        "color": "#ff7f00",
        "tooltip": ("Site of Community Importance / Special Area of Conservation "
                    "- Natura 2000 (EU Habitats Directive; French ZSC/SIC). "
                    "Activities that may harm the protected habitats can be "
                    "regulated and may require an environmental impact "
                    "assessment."),
        "highlight": ("Activities that may harm the protected habitats can be "
                      "regulated and may require an environmental impact "
                      "assessment."),
    },
    "fr_ep": {
        "label": "Protected Areas (PN / RN / APPB)",
        "color": "#6a3d9a",
        "tooltip": ("Regulatory protected area - a French national park core, "
                    "a national or regional nature reserve, or a biotope "
                    "protection order (APPB), each with its own rules and "
                    "managing body. APPBs in particular back many cliff "
                    "closures. Climbing, bivouacking, drones and organized "
                    "events are often regulated and may need authorization "
                    "from the managing body."),
        "highlight": ("Climbing, bivouacking, drones and organized "
                      "events are often regulated and may need authorization "
                      "from the managing body."),
    },
    # Switzerland. Federal wildlife reserves carry direct disturbance/access
    # rules; park restrictions depend on the park and its internal zones.
    "ch_game_reserves": {
        "label": "Federal Game Reserves",
        "color": "#e31a1c",
        "tooltip": ("Federal hunting-ban/game reserve protecting wild mammals, "
                    "birds and their habitats, with integral or partial "
                    "protection zones. Access and recreational activity can be "
                    "restricted; check the reserve object sheet and canton "
                    "before rigging."),
        "highlight": ("Access and recreational activity can be restricted; "
                      "check the reserve object sheet and canton before "
                      "rigging."),
    },
    "ch_bird_reserves": {
        "label": "Waterbird and Migratory Bird Reserves",
        "color": "#ff7f00",
        "tooltip": ("Federal reserve of international or national importance "
                    "for waterbirds and migratory birds. Access, water sports "
                    "and wildlife disturbance can be restricted; check the "
                    "reserve object sheet and canton before rigging."),
        "highlight": ("Access, water sports and wildlife disturbance can be "
                      "restricted; check the reserve object sheet and canton "
                      "before rigging."),
    },
    "ch_parks": {
        "label": "Swiss National and Regional Parks",
        "color": "#6a3d9a",
        "tooltip": ("Swiss National Park or park of national importance. "
                    "Highlining is not automatically prohibited across every "
                    "park, but protected zones and local rules may regulate "
                    "access, anchoring and organized activity; check with park "
                    "management before rigging."),
        "highlight": ("Highlining is not automatically prohibited across every "
                      "park, but protected zones and local rules may regulate "
                      "access, anchoring and organized activity; check with "
                      "park management before rigging."),
    },
}
