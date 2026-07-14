import L from "leaflet";
import { useEffect, useRef, useState } from "react";
import { ApiError, fetchDensity, fetchZones } from "@/lib/api";
import { bboxLonLatParam } from "@/lib/geo";
import type { useI18n } from "@/lib/i18n";
import { filterZonesByRestrictions } from "@/lib/restriction-filter";
import type { Lang } from "@/lib/i18n/strings";
import {
  DENSITY_MAX_ZOOM,
  DENSITY_TILE_MAX,
  DENSITY_TILE_MIN,
  DENSITY_ZOOM_OFFSET,
  zoneKey,
} from "@/lib/map-style";
import type {
  DensityFeatureCollection,
  RestrictionAreaMode,
  RestrictionFeatureCollection,
  ZoneFeatureCollection,
} from "@/types/highliner";
import { createDensityLayer, createZoneLayer } from "./leafletLayers";

type T = ReturnType<typeof useI18n>["t"];
type MapStatus = {
  kind: "idle" | "loading-zones" | "loading-density" | "zones" | "density" | "zoom" | "error";
  count?: number;
  detail?: string;
  noun?: "nounZones" | "nounHotspots";
};

export function useZoneDensityLayer(options: {
  mapRef: React.MutableRefObject<L.Map | null>;
  viewportRevision: number;
  minLen: number;
  maxLen: number;
  minExposure: number;
  lang: Lang;
  t: T;
  restrictionAreaMode: RestrictionAreaMode;
  restrictionFeatures: RestrictionFeatureCollection;
  onMapStatus?: (status: string) => void;
  onError?: (message: string) => void;
  onDensityModeChange?: (dense: boolean) => void;
}): { isLoading: boolean } {
  const zoneLayerRef = useRef<L.GeoJSON | null>(null);
  const densityLayerRef = useRef<L.GeoJSON | null>(null);
  const shownZoneKeysRef = useRef(new Set<string>());
  const shownZoneFeaturesRef = useRef<ZoneFeatureCollection["features"]>([]);
  const shownDensityRef = useRef<DensityFeatureCollection | null>(null);
  const densitySortedRef = useRef<number[]>([]);
  const requestIdRef = useRef(0);
  const layerLanguageRef = useRef<Lang | null>(null);
  const layerMapRef = useRef<L.Map | null>(null);
  const tRef = useRef(options.t);
  const restrictionAreaModeRef = useRef(options.restrictionAreaMode);
  const restrictionFeaturesRef = useRef(options.restrictionFeatures);
  const statusRef = useRef<MapStatus>({ kind: "idle" });
  const [isLoading, setIsLoading] = useState(false);
  const [mapReady, setMapReady] = useState(false);

  tRef.current = options.t;
  restrictionAreaModeRef.current = options.restrictionAreaMode;
  restrictionFeaturesRef.current = options.restrictionFeatures;

  function renderStatus() {
    switch (statusRef.current.kind) {
      case "loading-density":
        return tRef.current("loadingHotspots");
      case "loading-zones":
        return tRef.current("searching");
      case "zones":
        return tRef.current("zonesCount", { n: statusRef.current.count ?? 0 });
      case "density":
        return tRef.current("hotspotCells", { n: statusRef.current.count ?? 0 });
      case "zoom":
        return tRef.current("zoomInToSee", { noun: tRef.current(statusRef.current.noun ?? "nounZones") });
      case "error":
        return tRef.current("error", { detail: statusRef.current.detail ?? "" });
      default:
        return tRef.current("searching");
    }
  }

  function pushStatus(next: MapStatus) {
    statusRef.current = next;
    options.onMapStatus?.(renderStatus());
  }

  function renderZones() {
    const layer = zoneLayerRef.current;
    if (!layer) return;
    const collection: ZoneFeatureCollection = {
      type: "FeatureCollection",
      features: shownZoneFeaturesRef.current,
    };
    const visible = restrictionAreaModeRef.current === "informative"
      ? collection
      : filterZonesByRestrictions(
          collection,
          restrictionFeaturesRef.current,
        )
    layer.clearLayers();
    layer.addData(visible);
  }

  useEffect(() => {
    const map = options.mapRef.current;
    if (!map) return;
    if (
      layerMapRef.current === map
      && layerLanguageRef.current === options.lang
      && zoneLayerRef.current
      && densityLayerRef.current
    ) return;

    const previousMap = layerMapRef.current;
    if (zoneLayerRef.current) previousMap?.removeLayer(zoneLayerRef.current);
    if (densityLayerRef.current) previousMap?.removeLayer(densityLayerRef.current);

    zoneLayerRef.current = createZoneLayer(options.t).addTo(map);
    densityLayerRef.current = createDensityLayer(options.t, () => densitySortedRef.current).addTo(map);
    layerLanguageRef.current = options.lang;
    layerMapRef.current = map;

    renderZones();
    if (shownDensityRef.current) densityLayerRef.current.addData(shownDensityRef.current);
    if (!mapReady) setMapReady(true);

  });

  useEffect(() => {
    return () => {
      const map = layerMapRef.current;
      if (!map) return;
      if (zoneLayerRef.current) map.removeLayer(zoneLayerRef.current);
      if (densityLayerRef.current) map.removeLayer(densityLayerRef.current);
      zoneLayerRef.current = null;
      densityLayerRef.current = null;
      layerLanguageRef.current = null;
      layerMapRef.current = null;
    };
  }, [options.mapRef]);

  useEffect(() => {
    options.onMapStatus?.(renderStatus());
  }, [options.lang, options.onMapStatus]);

  useEffect(() => {
    zoneLayerRef.current?.clearLayers();
    shownZoneKeysRef.current.clear();
    shownZoneFeaturesRef.current = [];
  }, [options.minLen, options.maxLen, options.minExposure]);

  useEffect(() => {
    renderZones();
  }, [options.restrictionAreaMode, options.restrictionFeatures]);

  useEffect(() => {
    const map = options.mapRef.current;
    if (!map || !mapReady) return;
    const activeMap = map;
    const requestId = (requestIdRef.current += 1);
    const controller = new AbortController();
    const bboxLonLat = bboxLonLatParam(activeMap.getBounds());

    async function load() {
      const zoom = activeMap.getZoom();
      const densityMode = zoom <= DENSITY_MAX_ZOOM;
      options.onDensityModeChange?.(densityMode);
      pushStatus(densityMode ? { kind: "loading-density" } : { kind: "loading-zones" });
      setIsLoading(true);
      try {
        if (densityMode) {
          zoneLayerRef.current?.clearLayers();
          shownZoneKeysRef.current.clear();
          shownZoneFeaturesRef.current = [];
          const z = Math.min(
            Math.max(Math.round(zoom) + DENSITY_ZOOM_OFFSET, DENSITY_TILE_MIN),
            DENSITY_TILE_MAX,
          );
          const fc = await fetchDensity({ z, bboxLonLat }, controller.signal);
          if (requestId !== requestIdRef.current) return;
          densityLayerRef.current?.clearLayers();
          densitySortedRef.current = fc.features
            .map((feature) => feature.properties.n_pairs)
            .sort((a, b) => a - b);
          shownDensityRef.current = fc;
          densityLayerRef.current?.addData(fc);
          pushStatus({ kind: "density", count: fc.features.length });
          return;
        }

        densityLayerRef.current?.clearLayers();
        shownDensityRef.current = null;
        const fc = await fetchZones(
          { bboxLonLat, minLen: options.minLen, maxLen: options.maxLen, minExposure: options.minExposure },
          controller.signal,
        );
        if (requestId !== requestIdRef.current) return;
        const fresh = fc.features.filter((feature) => {
          const key = zoneKey(feature);
          if (shownZoneKeysRef.current.has(key)) return false;
          shownZoneKeysRef.current.add(key);
          return true;
        });
        shownZoneFeaturesRef.current = shownZoneFeaturesRef.current.concat(fresh);
        renderZones();
        pushStatus({ kind: "zones", count: shownZoneKeysRef.current.size });
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 413) {
          pushStatus({ kind: "zoom", noun: activeMap.getZoom() <= DENSITY_MAX_ZOOM ? "nounHotspots" : "nounZones" });
        } else {
          const detail = error instanceof Error ? error.message : String(error);
          const message = tRef.current("error", { detail });
          statusRef.current = { kind: "error", detail };
          options.onMapStatus?.(message);
          options.onError?.(message);
        }
      } finally {
        if (requestId === requestIdRef.current) setIsLoading(false);
      }
    }

    void load();
    return () => controller.abort();
  }, [
    options.mapRef,
    options.maxLen,
    options.minExposure,
    options.minLen,
    options.onDensityModeChange,
    options.onError,
    options.onMapStatus,
    options.viewportRevision,
    mapReady,
  ]);

  return { isLoading };
}
