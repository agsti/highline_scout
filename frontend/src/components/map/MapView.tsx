import L from "leaflet";
import { CopyIcon, ExternalLink, Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { captureMapSettled } from "@/lib/analytics";
import { ApiError, fetchAnchors, fetchRestrictions } from "@/lib/api";
import { bboxLonLatParam, type MapViewState } from "@/lib/geo";
import { useI18n } from "@/lib/i18n";
import { ANCHOR_MIN_ZOOM } from "@/lib/map-style";
import type { RestrictionLayerMeta } from "@/types/highliner";
import { createRestrictionLayer, renderAnchors } from "./leafletLayers";
import { useLeafletMap } from "./useLeafletMap";
import { useZoneDensityLayer } from "./useZoneDensityLayer";
import { ZoomControls } from "./ZoomControls";

const MOBILE_QUERY = "(max-width: 767px)";

interface MapViewProps {
  minLen: number;
  maxLen: number;
  minExposure: number;
  showAnchors: boolean;
  enabledRestrictions: string[];
  restrictionLayers: RestrictionLayerMeta[];
  onViewportChange: (map: L.Map) => void;
  onMapStatus?: (status: string) => void;
  onAnchorStatus?: (status: string) => void;
  onRestrictionStatus?: (status: string) => void;
  onError?: (message: string) => void;
  onViewStateChange?: (view: MapViewState) => void;
  onDensityModeChange?: (dense: boolean) => void;
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
  minLen,
  maxLen,
  minExposure,
  showAnchors,
  enabledRestrictions,
  restrictionLayers,
  onViewportChange,
  onMapStatus,
  onAnchorStatus,
  onRestrictionStatus,
  onError,
  onViewStateChange,
  onDensityModeChange,
}: MapViewProps) {
  const { lang, t } = useI18n();
  const [mapElement, setMapElement] = useState<HTMLDivElement | null>(null);
  const mapForContextRef = useRef<L.Map | null>(null);
  const anchorLayerRef = useRef<L.LayerGroup | null>(null);
  const restrictionLayerRef = useRef<L.GeoJSON | null>(null);
  const restrictionMetaRef = useRef(new Map<string, RestrictionLayerMeta>());
  const contextMenuRootRef = useRef<HTMLDivElement | null>(null);
  const keepContextMenuForMoveRef = useRef(false);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  const setMapElementRef = useCallback((element: HTMLDivElement | null) => {
    setMapElement(element);
  }, []);

  const handleViewportChange = useCallback((map: L.Map) => {
    mapForContextRef.current = map;
    if (keepContextMenuForMoveRef.current) {
      keepContextMenuForMoveRef.current = false;
    } else {
      setContextMenu(null);
    }
    onViewportChange(map);
  }, [onViewportChange]);

  function isMobileViewport() {
    return typeof window.matchMedia === "function" && window.matchMedia(MOBILE_QUERY).matches;
  }

  const setContextMenuFromLeafletEvent = useCallback((event: L.LeafletMouseEvent) => {
    const map = mapForContextRef.current;
    if (!map) return;
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
  }, []);

  const onMapSettled = useCallback((map: L.Map) => {
    const center = map.getCenter();
    captureMapSettled(map.getZoom(), center.lat, center.lng);
  }, []);

  const { mapRef, viewportRevision } = useLeafletMap({
    element: mapElement,
    t,
    lang,
    onViewportChange: handleViewportChange,
    onViewStateChange,
    onMapSettled,
    onContextMenu: setContextMenuFromLeafletEvent,
  });

  const { isLoading } = useZoneDensityLayer({
    mapRef,
    viewportRevision,
    minLen,
    maxLen,
    minExposure,
    lang,
    t,
    onMapStatus,
    onError,
    onDensityModeChange,
  });

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
    const map = mapRef.current;
    if (!map) return;
    anchorLayerRef.current = L.layerGroup().addTo(map);
    restrictionLayerRef.current = createRestrictionLayer(() => restrictionMetaRef.current).addTo(map);
    return () => {
      anchorLayerRef.current = null;
      restrictionLayerRef.current = null;
    };
  }, [mapElement, mapRef]);

  useEffect(() => {
    restrictionMetaRef.current = new Map(restrictionLayers.map((layer) => [layer.id, layer]));
  }, [restrictionLayers]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = anchorLayerRef.current;
    if (!map || !layer) return;
    if (!showAnchors) {
      layer.clearLayers();
      onAnchorStatus?.("");
      return;
    }
    if (map.getZoom() < ANCHOR_MIN_ZOOM) {
      layer.clearLayers();
      onAnchorStatus?.(t("zoomInToSee", { noun: t("nounAnchors") }));
      return;
    }
    const controller = new AbortController();
    fetchAnchors({ bboxLonLat: bboxLonLatParam(map.getBounds()) }, controller.signal)
      .then((fc) => {
        renderAnchors(layer, fc);
        onAnchorStatus?.(t("anchorsCount", { n: fc.features.length }));
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        layer.clearLayers();
        const message = t("anchorError", { detail: error instanceof Error ? error.message : String(error) });
        onAnchorStatus?.(message);
        onError?.(message);
      });
    return () => controller.abort();
  }, [mapElement, showAnchors, t, onAnchorStatus, onError, viewportRevision]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = restrictionLayerRef.current;
    if (!map || !layer) return;
    if (enabledRestrictions.length === 0) {
      layer.clearLayers();
      onRestrictionStatus?.("");
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
        onRestrictionStatus?.(t("protectedAreasCount", { n: fc.features.length }));
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        layer.clearLayers();
        if (error instanceof ApiError && error.status === 413) {
          onRestrictionStatus?.(t("zoomInToSee", { noun: t("nounProtectedAreas") }));
        } else {
          const message = t("error", { detail: error instanceof Error ? error.message : String(error) });
          onRestrictionStatus?.(message);
          onError?.(message);
        }
      });
    return () => controller.abort();
  }, [enabledRestrictions, mapElement, t, onRestrictionStatus, onError, viewportRevision]);

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
      <div ref={setMapElementRef} className="h-full w-full" />
      {isLoading ? (
        <div
          data-testid="map-spinner"
          role="status"
          aria-live="polite"
          className="pointer-events-none absolute inset-0 z-[1100] flex items-center justify-center"
        >
          <div className="rounded-full bg-background/85 p-3 shadow-lg backdrop-blur">
            <Loader2 className="h-8 w-8 animate-spin text-primary" aria-hidden="true" />
            <span className="sr-only">{t("searching")}</span>
          </div>
        </div>
      ) : null}
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
      <ZoomControls
        onZoomIn={() => mapRef.current?.zoomIn()}
        onZoomOut={() => mapRef.current?.zoomOut()}
      />
    </div>
  );
}
