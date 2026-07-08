import L from "leaflet";
import { densityRank, tealShade, ZONE_COLOR } from "@/lib/map-style";
import type { DensityFeature, ZoneFeature } from "@/types/highliner";
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
    },
  });
}

export function createDensityLayer(t: T, sortedCounts: () => number[]): L.GeoJSON {
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
