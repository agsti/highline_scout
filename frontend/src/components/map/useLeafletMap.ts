import L from "leaflet";
import { useEffect, useRef, useState } from "react";
import type { useI18n } from "@/lib/i18n";
import { initialViewFromSearch, type MapViewState } from "@/lib/geo";
import type { Lang } from "@/lib/i18n/strings";

const DEFAULT_VIEW: MapViewState = { center: [41.6, 1.83], zoom: 13 };

type T = ReturnType<typeof useI18n>["t"];

export interface LeafletMapState {
  mapRef: React.MutableRefObject<L.Map | null>;
  viewportRevision: number;
}

export function useLeafletMap(options: {
  element: HTMLElement | null;
  t: T;
  lang: Lang;
  onViewportChange: (map: L.Map) => void;
  onViewStateChange?: (view: MapViewState) => void;
  onMapSettled: (map: L.Map) => void;
  onContextMenu: (event: L.LeafletMouseEvent) => void;
}): LeafletMapState {
  const mapRef = useRef<L.Map | null>(null);
  const callbacksRef = useRef(options);
  const [viewportRevision, setViewportRevision] = useState(0);

  callbacksRef.current = options;

  useEffect(() => {
    if (!options.element || mapRef.current) return;

    const view = initialViewFromSearch(window.location.search) ?? DEFAULT_VIEW;
    const map = L.map(options.element, { zoomControl: false }).setView(view.center, view.zoom);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "(c) OpenStreetMap",
    }).addTo(map);
    map.createPane("restrictions");
    const pane = map.getPane("restrictions");
    if (pane) pane.style.zIndex = "350";

    map.on("moveend", () => {
      const callbacks = callbacksRef.current;
      callbacks.onViewportChange(map);
      const center = map.getCenter();
      callbacks.onViewStateChange?.({ center: [center.lat, center.lng], zoom: map.getZoom() });
      callbacks.onMapSettled(map);
      setViewportRevision((revision) => revision + 1);
    });
    map.on("contextmenu", (event) => callbacksRef.current.onContextMenu(event));

    mapRef.current = map;
    callbacksRef.current.onViewportChange(map);
    const center = map.getCenter();
    callbacksRef.current.onViewStateChange?.({ center: [center.lat, center.lng], zoom: map.getZoom() });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [options.element]);

  return { mapRef, viewportRevision };
}
