import L from "leaflet";
import { useEffect, useRef, useState } from "react";
import { ApiError, fetchDensity, fetchZones } from "@/lib/api";
import { bboxLonLatParam, initialViewFromSearch, type MapViewState } from "@/lib/geo";
import { useI18n } from "@/lib/i18n";
import {
  DENSITY_MAX_ZOOM,
  DENSITY_TILE_MAX,
  DENSITY_TILE_MIN,
  DENSITY_ZOOM_OFFSET,
  zoneKey,
} from "@/lib/map-style";
import type { Region, ZoneFeatureCollection } from "@/types/highliner";
import { createDensityLayer, createZoneLayer } from "./leafletLayers";

const DEFAULT_VIEW: MapViewState = { center: [41.6, 1.83], zoom: 13 };

interface MapViewProps {
  regions: Region[];
  region: string;
  maxLen: number;
  minExposure: number;
  onViewportChange: (map: L.Map) => void;
  onMapStatus: (status: string) => void;
}

export function MapView({ regions, region, maxLen, minExposure, onViewportChange, onMapStatus }: MapViewProps) {
  const { t } = useI18n();
  const elRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const skipInitialRegionFitRef = useRef(false);
  const zoneLayerRef = useRef<L.GeoJSON | null>(null);
  const densityLayerRef = useRef<L.GeoJSON | null>(null);
  const shownZoneKeysRef = useRef(new Set<string>());
  const densitySortedRef = useRef<number[]>([]);
  const requestIdRef = useRef(0);
  const [viewportTick, setViewportTick] = useState(0);

  useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    const urlView = initialViewFromSearch(window.location.search);
    skipInitialRegionFitRef.current = !!urlView;
    const view = urlView ?? DEFAULT_VIEW;
    const map = L.map(elRef.current).setView(view.center, view.zoom);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "(c) OpenStreetMap",
    }).addTo(map);
    zoneLayerRef.current = createZoneLayer(t).addTo(map);
    densityLayerRef.current = createDensityLayer(t, () => densitySortedRef.current).addTo(map);
    map.on("moveend", () => {
      onViewportChange(map);
      setViewportTick((value) => value + 1);
    });
    mapRef.current = map;
    onViewportChange(map);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [onViewportChange]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !region) return;
    const selected = regions.find((item) => item.name === region);
    if (!selected) return;
    if (skipInitialRegionFitRef.current) {
      skipInitialRegionFitRef.current = false;
      return;
    }
    const [w, s, e, n] = selected.bounds_lonlat;
    map.fitBounds([
      [s, w],
      [n, e],
    ]);
  }, [region, regions]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !region) return;
    const activeMap = map;
    const requestId = (requestIdRef.current += 1);
    const controller = new AbortController();
    const bboxLonLat = bboxLonLatParam(activeMap.getBounds());

    async function load() {
      const zoom = activeMap.getZoom();
      onMapStatus(zoom <= DENSITY_MAX_ZOOM ? t("loadingHotspots") : t("searching"));
      try {
        if (zoom <= DENSITY_MAX_ZOOM) {
          zoneLayerRef.current?.clearLayers();
          shownZoneKeysRef.current.clear();
          const z = Math.min(
            Math.max(Math.round(zoom) + DENSITY_ZOOM_OFFSET, DENSITY_TILE_MIN),
            DENSITY_TILE_MAX,
          );
          const fc = await fetchDensity({ region, z, bboxLonLat }, controller.signal);
          if (requestId !== requestIdRef.current) return;
          densityLayerRef.current?.clearLayers();
          densitySortedRef.current = fc.features
            .map((feature) => feature.properties.n_pairs)
            .sort((a, b) => a - b);
          densityLayerRef.current?.addData(fc);
          onMapStatus(t("hotspotCells", { n: fc.features.length }));
          return;
        }

        densityLayerRef.current?.clearLayers();
        const fc = await fetchZones({ region, bboxLonLat, maxLen, minExposure }, controller.signal);
        if (requestId !== requestIdRef.current) return;
        const fresh = fc.features.filter((feature) => {
          const key = zoneKey(feature);
          if (shownZoneKeysRef.current.has(key)) return false;
          shownZoneKeysRef.current.add(key);
          return true;
        });
        const freshCollection: ZoneFeatureCollection = { type: "FeatureCollection", features: fresh };
        zoneLayerRef.current?.addData(freshCollection);
        onMapStatus(t("zonesCount", { n: shownZoneKeysRef.current.size }));
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 413) {
          onMapStatus(
            t("zoomInToSee", { noun: t(activeMap.getZoom() <= DENSITY_MAX_ZOOM ? "nounHotspots" : "nounZones") }),
          );
        } else {
          onMapStatus(t("error", { detail: error instanceof Error ? error.message : String(error) }));
        }
      }
    }

    void load();
    return () => controller.abort();
  }, [region, maxLen, minExposure, t, onMapStatus, viewportTick]);

  useEffect(() => {
    zoneLayerRef.current?.clearLayers();
    shownZoneKeysRef.current.clear();
  }, [region, maxLen, minExposure]);

  useEffect(() => {
    const timeout = window.setTimeout(() => mapRef.current?.invalidateSize(), 250);
    return () => window.clearTimeout(timeout);
  });

  return <div ref={elRef} className="h-full w-full" />;
}
