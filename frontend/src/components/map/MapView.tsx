import L from "leaflet";
import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { captureMapSettled } from "@/lib/analytics";
import { bboxLonLatParam, type MapViewState } from "@/lib/geo";
import { useI18n } from "@/lib/i18n";
import type {
  RestrictionAreaMode,
  RestrictionFeatureCollection,
  RestrictionLayerMeta,
} from "@/types/highliner";
import { MapContextMenu, type ContextMenuPoint } from "./MapContextMenu";
import { useAnchorLayer } from "./useAnchorLayer";
import { useLeafletMap } from "./useLeafletMap";
import { useRestrictionLayer } from "./useRestrictionLayer";
import { useZoneDensityLayer } from "./useZoneDensityLayer";
import { ZoomControls } from "./ZoomControls";

const MOBILE_QUERY = "(max-width: 767px)";

interface MapViewProps {
  minLen: number;
  maxLen: number;
  minExposure: number;
  showAnchors: boolean;
  restrictionAreaMode: RestrictionAreaMode;
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

export function MapView({
  minLen,
  maxLen,
  minExposure,
  showAnchors,
  restrictionAreaMode,
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
  const keepContextMenuForMoveRef = useRef(false);
  const [contextMenu, setContextMenu] = useState<ContextMenuPoint | null>(null);
  const [restrictionFeatures, setRestrictionFeatures] = useState<RestrictionFeatureCollection>({
    type: "FeatureCollection",
    features: [],
  });

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
    restrictionAreaMode,
    restrictionFeatures,
    onMapStatus,
    onError,
    onDensityModeChange,
  });

  useAnchorLayer({
    mapRef,
    viewportRevision,
    showAnchors,
    t,
    onAnchorStatus,
    onError,
  });

  useRestrictionLayer({
    mapRef,
    viewportRevision,
    enabledRestrictions,
    restrictionLayers,
    t,
    onFeaturesChange: setRestrictionFeatures,
    onRestrictionStatus,
    onError,
  });

  useEffect(() => {
    const timeout = window.setTimeout(() => mapRef.current?.invalidateSize(), 250);
    return () => window.clearTimeout(timeout);
  });

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
      <MapContextMenu point={contextMenu} t={t} onDismiss={() => setContextMenu(null)} />
      <ZoomControls
        onZoomIn={() => mapRef.current?.zoomIn()}
        onZoomOut={() => mapRef.current?.zoomOut()}
      />
    </div>
  );
}
