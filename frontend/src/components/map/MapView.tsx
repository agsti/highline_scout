import L from "leaflet";
import { useEffect, useRef } from "react";
import { initialViewFromSearch, type MapViewState } from "@/lib/geo";
import type { Region } from "@/types/highliner";

const DEFAULT_VIEW: MapViewState = { center: [41.6, 1.83], zoom: 13 };

interface MapViewProps {
  regions: Region[];
  region: string;
  onViewportChange: (map: L.Map) => void;
}

export function MapView({ regions, region, onViewportChange }: MapViewProps) {
  const elRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const usedUrlViewRef = useRef(false);

  useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    const urlView = initialViewFromSearch(window.location.search);
    usedUrlViewRef.current = !!urlView;
    const view = urlView ?? DEFAULT_VIEW;
    const map = L.map(elRef.current).setView(view.center, view.zoom);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "(c) OpenStreetMap",
    }).addTo(map);
    map.on("moveend", () => onViewportChange(map));
    mapRef.current = map;
    onViewportChange(map);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [onViewportChange]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !region || usedUrlViewRef.current) {
      usedUrlViewRef.current = false;
      return;
    }
    const selected = regions.find((item) => item.name === region);
    if (!selected) return;
    const [w, s, e, n] = selected.bounds_lonlat;
    map.fitBounds([
      [s, w],
      [n, e],
    ]);
  }, [region, regions]);

  useEffect(() => {
    const timeout = window.setTimeout(() => mapRef.current?.invalidateSize(), 250);
    return () => window.clearTimeout(timeout);
  });

  return <div ref={elRef} className="h-full w-full" />;
}
