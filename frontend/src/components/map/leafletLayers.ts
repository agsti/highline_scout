import L from "leaflet";
import { capture } from "@/lib/analytics";
import { wedge } from "@/lib/geo";
import { ANCHOR_COLOR, ANCHOR_DETAIL_LIMIT, ANCHOR_WEDGE_RADIUS_M, densityRank, tealShade, ZONE_COLOR } from "@/lib/map-style";
import type {
  AnchorFeatureCollection,
  DensityFeature,
  RestrictionFeature,
  RestrictionLayerMeta,
  ZoneFeature,
} from "@/types/highliner";
import { densityTooltipHtml, zonePopupHtml } from "./popups";
import type { StringKey } from "@/lib/i18n";

type T = (key: StringKey, params?: Record<string, string | number>) => string;

export function createZoneLayer(t: T): L.GeoJSON {
  return L.geoJSON(undefined, {
    style: () => ({
      color: ZONE_COLOR,
      weight: 2,
      fillOpacity: 0.35,
    }),
    onEachFeature: (feature, layer) => {
      const zone = feature as ZoneFeature;
      layer.bindPopup(zonePopupHtml(zone.properties, t));
      layer.on("popupopen", () => {
        const { length_min, length_max, height_max, n_pairs } = zone.properties;
        capture("zone_opened", { length_min, length_max, height_max, n_pairs });
      });
    },
  });
}

export function createDensityLayer(
  t: T,
  sortedCounts: () => number[],
): L.GeoJSON {
  return L.geoJSON(undefined, {
    style: (feature) => {
      const density = feature as DensityFeature;
      const rank = densityRank(density.properties.n_pairs, sortedCounts());
      return {
        color: tealShade(Math.min(rank + 0.15, 1)),
        weight: 0.5,
        fillColor: tealShade(rank),
        fillOpacity: 0.2 + 0.55 * rank,
      };
    },
    onEachFeature: (feature, layer) => {
      const density = feature as DensityFeature;
      layer.bindTooltip(densityTooltipHtml(density.properties, t));
    },
  });
}

export function renderAnchors(layer: L.LayerGroup, fc: AnchorFeatureCollection): void {
  layer.clearLayers();
  const detailed = fc.features.length <= ANCHOR_DETAIL_LIMIT;
  const canvas = L.canvas({ padding: 0.5 });
  for (const feature of fc.features) {
    const [lon, lat] = feature.geometry.coordinates;
    if (detailed) {
      for (const sector of feature.properties.sectors) {
        L.polygon(wedge(lat, lon, sector[0], sector[1], ANCHOR_WEDGE_RADIUS_M), {
          color: ANCHOR_COLOR,
          weight: 1,
          fillOpacity: 0.25,
        }).addTo(layer);
      }
      L.circleMarker([lat, lon], {
        radius: 4,
        color: ANCHOR_COLOR,
        weight: 1,
        fillOpacity: 1,
      })
        .addTo(layer);
    } else {
      L.circleMarker([lat, lon], {
        renderer: canvas,
        radius: 2,
        color: ANCHOR_COLOR,
        weight: 1,
        fillOpacity: 0.8,
      })
        .addTo(layer);
    }
  }
}

export function createRestrictionLayer(metaById: () => Map<string, RestrictionLayerMeta>): L.GeoJSON {
  return L.geoJSON(undefined, {
    pane: "restrictions",
    style: (feature) => {
      const restriction = feature as RestrictionFeature;
      return {
        color: metaById().get(restriction.properties.layer)?.color ?? "#888",
        weight: 1,
        fillOpacity: 0.15,
      };
    },
    onEachFeature: (feature, layer) => {
      const restriction = feature as RestrictionFeature;
      const meta = metaById().get(restriction.properties.layer);
      layer.bindPopup(
        `<b>${meta?.label ?? restriction.properties.layer}</b>${restriction.properties.name ? `<br>${restriction.properties.name}` : ""}`,
      );
    },
  });
}
