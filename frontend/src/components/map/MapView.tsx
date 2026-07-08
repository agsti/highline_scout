import L from "leaflet";
import { CopyIcon, ExternalLink } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, fetchAnchors, fetchDensity, fetchRestrictions, fetchZones } from "@/lib/api";
import { bboxLonLatParam, initialViewFromSearch, type MapViewState } from "@/lib/geo";
import { useI18n } from "@/lib/i18n";
import {
  ANCHOR_MIN_ZOOM,
  DENSITY_MAX_ZOOM,
  DENSITY_TILE_MAX,
  DENSITY_TILE_MIN,
  DENSITY_ZOOM_OFFSET,
  tealShade,
  zoneKey,
} from "@/lib/map-style";
import type { DensityFeatureCollection, Region, RestrictionLayerMeta, ZoneFeatureCollection } from "@/types/highliner";
import { createDensityLayer, createRestrictionLayer, createZoneLayer, renderAnchors } from "./leafletLayers";

const DEFAULT_VIEW: MapViewState = { center: [41.6, 1.83], zoom: 13 };
const MOBILE_QUERY = "(max-width: 767px)";

interface MapViewProps {
  regions: Region[];
  region: string;
  maxLen: number;
  minExposure: number;
  showAnchors: boolean;
  enabledRestrictions: string[];
  restrictionLayers: RestrictionLayerMeta[];
  onViewportChange: (map: L.Map) => void;
  onMapStatus: (status: string) => void;
  onAnchorStatus: (status: string) => void;
  onRestrictionStatus: (status: string) => void;
  onViewStateChange?: (view: MapViewState) => void;
}

export async function copyViewportLink(lat: number, lng: number, zoom: number, t: T) {
  const params = new URLSearchParams({ lat: lat.toFixed(5), lng: lng.toFixed(5), z: String(zoom) });
  const url = `${window.location.origin}${window.location.pathname}?${params}`;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(url);
    return;
  }
  window.prompt(t("copyLink"), url);
}

type T = ReturnType<typeof useI18n>["t"];

interface ContextMenuState {
  lat: number;
  lng: number;
  zoom: number;
  x: number;
  y: number;
}

export function MapView({
  regions,
  region,
  maxLen,
  minExposure,
  showAnchors,
  enabledRestrictions,
  restrictionLayers,
  onViewportChange,
  onMapStatus,
  onAnchorStatus,
  onRestrictionStatus,
  onViewStateChange,
}: MapViewProps) {
  const { lang, t } = useI18n();
  const elRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const skipInitialRegionFitRef = useRef(false);
  const zoneLayerRef = useRef<L.GeoJSON | null>(null);
  const densityLayerRef = useRef<L.GeoJSON | null>(null);
  const anchorLayerRef = useRef<L.LayerGroup | null>(null);
  const restrictionLayerRef = useRef<L.GeoJSON | null>(null);
  const restrictionMetaRef = useRef(new Map<string, RestrictionLayerMeta>());
  const shownZoneKeysRef = useRef(new Set<string>());
  const shownZoneFeaturesRef = useRef<ZoneFeatureCollection["features"]>([]);
  const shownDensityRef = useRef<DensityFeatureCollection | null>(null);
  const densitySortedRef = useRef<number[]>([]);
  const requestIdRef = useRef(0);
  const tRef = useRef(t);
  const contextMenuRootRef = useRef<HTMLDivElement | null>(null);
  const keepContextMenuForMoveRef = useRef(false);
  const statusRef = useRef<{ kind: "idle" | "loading-zones" | "loading-density" | "zones" | "density" | "zoom" | "error"; count?: number; detail?: string; noun?: "nounZones" | "nounHotspots" }>({ kind: "idle" });
  const [viewportTick, setViewportTick] = useState(0);
  const [showDensityLegend, setShowDensityLegend] = useState(false);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  function renderStatus() {
    switch (statusRef.current.kind) {
      case "loading-density":
        return t("loadingHotspots");
      case "loading-zones":
        return t("searching");
      case "zones":
        return t("zonesCount", { n: statusRef.current.count ?? 0 });
      case "density":
        return t("hotspotCells", { n: statusRef.current.count ?? 0 });
      case "zoom":
        return t("zoomInToSee", { noun: t(statusRef.current.noun ?? "nounZones") });
      case "error":
        return t("error", { detail: statusRef.current.detail ?? "" });
      default:
        return t("searching");
    }
  }

  function pushStatus(next: typeof statusRef.current) {
    statusRef.current = next;
    onMapStatus(renderStatus());
  }

  function publishViewState(map: L.Map) {
    const center = map.getCenter();
    onViewStateChange?.({ center: [center.lat, center.lng], zoom: map.getZoom() });
  }

  function rebuildDynamicLayers(map: L.Map) {
    if (zoneLayerRef.current) map.removeLayer(zoneLayerRef.current);
    if (densityLayerRef.current) map.removeLayer(densityLayerRef.current);

    zoneLayerRef.current = createZoneLayer(t).addTo(map);
    densityLayerRef.current = createDensityLayer(t, () => densitySortedRef.current).addTo(map);

    if (shownZoneFeaturesRef.current.length > 0) {
      const collection: ZoneFeatureCollection = {
        type: "FeatureCollection",
        features: shownZoneFeaturesRef.current,
      };
      zoneLayerRef.current.addData(collection);
    }
    if (shownDensityRef.current) {
      densityLayerRef.current.addData(shownDensityRef.current);
    }
  }

  function isMobileViewport() {
    return typeof window.matchMedia === "function" && window.matchMedia(MOBILE_QUERY).matches;
  }

  useEffect(() => {
    tRef.current = t;
  }, [t]);

  useEffect(() => {
    if (!contextMenu) return;

    function onPointerDown(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && contextMenuRootRef.current?.contains(target)) return;
      setContextMenu(null);
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setContextMenu(null);
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [contextMenu]);

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
    map.createPane("restrictions");
    const pane = map.getPane("restrictions");
    if (pane) pane.style.zIndex = "350";
    rebuildDynamicLayers(map);
    anchorLayerRef.current = L.layerGroup().addTo(map);
    restrictionLayerRef.current = createRestrictionLayer(() => restrictionMetaRef.current).addTo(map);
    map.on("moveend", () => {
      if (keepContextMenuForMoveRef.current) {
        keepContextMenuForMoveRef.current = false;
      } else {
        setContextMenu(null);
      }
      onViewportChange(map);
      publishViewState(map);
      setViewportTick((value) => value + 1);
    });
    map.on("contextmenu", (event) => {
      const { lat, lng } = event.latlng;
      const mobile = isMobileViewport();
      setContextMenu({
        lat,
        lng,
        zoom: map.getZoom(),
        x: event.containerPoint.x,
        y: event.containerPoint.y,
      });
      if (mobile) {
        keepContextMenuForMoveRef.current = true;
        map.panTo([lat, lng], { animate: true });
      }
    });
    mapRef.current = map;
    onViewportChange(map);
    publishViewState(map);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [onViewportChange, onViewStateChange]);

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
    if (!map) return;
    rebuildDynamicLayers(map);
    onMapStatus(renderStatus());
  }, [lang, onMapStatus]);

  useEffect(() => {
    restrictionMetaRef.current = new Map(restrictionLayers.map((layer) => [layer.id, layer]));
  }, [restrictionLayers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !region) return;
    const activeMap = map;
    const requestId = (requestIdRef.current += 1);
    const controller = new AbortController();
    const bboxLonLat = bboxLonLatParam(activeMap.getBounds());

    async function load() {
      const zoom = activeMap.getZoom();
      const densityMode = zoom <= DENSITY_MAX_ZOOM;
      setShowDensityLegend(densityMode);
      pushStatus(densityMode ? { kind: "loading-density" } : { kind: "loading-zones" });
      try {
        if (densityMode) {
          zoneLayerRef.current?.clearLayers();
          shownZoneKeysRef.current.clear();
          shownZoneFeaturesRef.current = [];
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
          shownDensityRef.current = fc;
          densityLayerRef.current?.addData(fc);
          pushStatus({ kind: "density", count: fc.features.length });
          return;
        }

        densityLayerRef.current?.clearLayers();
        shownDensityRef.current = null;
        const fc = await fetchZones({ region, bboxLonLat, maxLen, minExposure }, controller.signal);
        if (requestId !== requestIdRef.current) return;
        const fresh = fc.features.filter((feature) => {
          const key = zoneKey(feature);
          if (shownZoneKeysRef.current.has(key)) return false;
          shownZoneKeysRef.current.add(key);
          return true;
        });
        shownZoneFeaturesRef.current = shownZoneFeaturesRef.current.concat(fresh);
        const freshCollection: ZoneFeatureCollection = { type: "FeatureCollection", features: fresh };
        zoneLayerRef.current?.addData(freshCollection);
        pushStatus({ kind: "zones", count: shownZoneKeysRef.current.size });
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 413) {
          pushStatus({ kind: "zoom", noun: activeMap.getZoom() <= DENSITY_MAX_ZOOM ? "nounHotspots" : "nounZones" });
        } else {
          pushStatus({ kind: "error", detail: error instanceof Error ? error.message : String(error) });
        }
      }
    }

    void load();
    return () => controller.abort();
  }, [region, maxLen, minExposure, onMapStatus, viewportTick]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = anchorLayerRef.current;
    if (!map || !layer || !region) return;
    if (!showAnchors) {
      layer.clearLayers();
      onAnchorStatus("");
      return;
    }
    if (map.getZoom() < ANCHOR_MIN_ZOOM) {
      layer.clearLayers();
      onAnchorStatus(t("zoomInToSee", { noun: t("nounAnchors") }));
      return;
    }
    const controller = new AbortController();
    fetchAnchors({ region, bboxLonLat: bboxLonLatParam(map.getBounds()) }, controller.signal)
      .then((fc) => {
        renderAnchors(layer, fc, t);
        onAnchorStatus(t("anchorsCount", { n: fc.features.length }));
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        layer.clearLayers();
        onAnchorStatus(t("anchorError", { detail: error instanceof Error ? error.message : String(error) }));
      });
    return () => controller.abort();
  }, [region, showAnchors, t, onAnchorStatus, viewportTick]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = restrictionLayerRef.current;
    if (!map || !layer) return;
    if (enabledRestrictions.length === 0) {
      layer.clearLayers();
      onRestrictionStatus("");
      return;
    }
    const controller = new AbortController();
    fetchRestrictions(
      { bboxLonLat: bboxLonLatParam(map.getBounds()), layers: enabledRestrictions },
      controller.signal,
    )
      .then((fc) => {
        layer.clearLayers();
        layer.addData(fc);
        onRestrictionStatus(t("protectedAreasCount", { n: fc.features.length }));
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        layer.clearLayers();
        if (error instanceof ApiError && error.status === 413) {
          onRestrictionStatus(t("zoomInToSee", { noun: t("nounProtectedAreas") }));
        } else {
          onRestrictionStatus(t("error", { detail: error instanceof Error ? error.message : String(error) }));
        }
      });
    return () => controller.abort();
  }, [enabledRestrictions, t, onRestrictionStatus, viewportTick]);

  useEffect(() => {
    zoneLayerRef.current?.clearLayers();
    shownZoneKeysRef.current.clear();
    shownZoneFeaturesRef.current = [];
  }, [region, maxLen, minExposure]);

  useEffect(() => {
    const timeout = window.setTimeout(() => mapRef.current?.invalidateSize(), 250);
    return () => window.clearTimeout(timeout);
  });

  async function copyContextMenuLink() {
    if (!contextMenu) return;
    await copyViewportLink(contextMenu.lat, contextMenu.lng, contextMenu.zoom, t);
    setContextMenu(null);
  }

  const contextGoogleMapsHref = contextMenu
    ? `https://www.google.com/maps?q=${contextMenu.lat},${contextMenu.lng}`
    : "#";

  return (
    <div className="relative h-full w-full">
      <div ref={elRef} className="h-full w-full" />
      {contextMenu ? (
        <div ref={contextMenuRootRef} className="pointer-events-none absolute inset-0 z-[1200]">
          <div
            data-testid="mobile-context-point-marker"
            className="pointer-events-none absolute left-1/2 top-1/2 h-10 w-10 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-primary bg-primary/15 shadow-[0_0_0_4px_hsl(var(--background)),0_0_0_8px_hsl(var(--primary)/0.35),0_8px_24px_hsl(var(--foreground)/0.35)] after:absolute after:left-1/2 after:top-1/2 after:h-3 after:w-3 after:-translate-x-1/2 after:-translate-y-1/2 after:rounded-full after:bg-primary after:shadow-[0_0_0_2px_hsl(var(--background))] md:hidden"
            aria-hidden="true"
          />
          <div
            data-testid="desktop-context-menu"
            className="pointer-events-auto absolute hidden min-w-56 overflow-hidden rounded-md border bg-background/98 p-1 text-sm shadow-xl backdrop-blur md:block"
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            <a
              className="block rounded-sm px-3 py-2 font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              href={contextGoogleMapsHref}
              target="_blank"
              rel="noopener"
            >
              {t("viewInGoogleMaps")}
            </a>
            <button
              type="button"
              className="block w-full rounded-sm px-3 py-2 text-left font-medium hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              onClick={() => void copyContextMenuLink()}
            >
              {t("copyLink")}
            </button>
          </div>

          <div
            data-testid="mobile-context-menu"
            className="pointer-events-auto fixed inset-0 z-[1200] flex items-end bg-black/35 p-3 md:hidden"
            onClick={() => setContextMenu(null)}
          >
            <div
              className="w-full rounded-xl border bg-background p-3 shadow-xl"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-border" />
              <h2 className="mb-3 px-1 text-sm font-semibold">{t("pointActions")}</h2>
              <div className="grid gap-2">
                <Button
                  asChild
                  type="button"
                  variant="outline"
                  className="h-11 w-full justify-start"
                >
                  <a href={contextGoogleMapsHref} target="_blank" rel="noopener">
                    <ExternalLink className="h-4 w-4" />
                    {t("viewInGoogleMaps")}
                  </a>
                </Button>
                <Button type="button" variant="outline" className="h-11 w-full justify-start" onClick={() => void copyContextMenuLink()}>
                  <CopyIcon className="h-4 w-4" />
                  {t("copyLink")}
                </Button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      {showDensityLegend ? (
        <div className="pointer-events-none absolute bottom-3 right-3 rounded-md border bg-background/95 px-3 py-2 text-xs shadow">
          <div className="mb-1 font-medium">{t("lineDensity")}</div>
          <div className="flex gap-px">
            {[0, 0.25, 0.5, 0.75, 1].map((value) => (
              <span
                key={value}
                className="block h-2 w-6"
                style={{ backgroundColor: tealShade(value) }}
              />
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
            <span>{t("sparse")}</span>
            <span>{t("dense")}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
