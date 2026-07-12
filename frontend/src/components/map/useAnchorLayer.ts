import L from "leaflet";
import { useEffect, useRef, useState } from "react";
import { fetchAnchors } from "@/lib/api";
import { bboxLonLatParam } from "@/lib/geo";
import type { useI18n } from "@/lib/i18n";
import { ANCHOR_MIN_ZOOM } from "@/lib/map-style";
import { renderAnchors } from "./leafletLayers";

type T = ReturnType<typeof useI18n>["t"];

export function useAnchorLayer(options: {
  mapRef: React.MutableRefObject<L.Map | null>;
  viewportRevision: number;
  showAnchors: boolean;
  t: T;
  onAnchorStatus?: (status: string) => void;
  onError?: (message: string) => void;
}): void {
  const layerRef = useRef<L.LayerGroup | null>(null);
  const layerMapRef = useRef<L.Map | null>(null);
  const [layerRevision, setLayerRevision] = useState(0);

  useEffect(() => {
    const map = options.mapRef.current;
    if (!map || layerMapRef.current === map) return;
    if (layerRef.current) layerMapRef.current?.removeLayer(layerRef.current);
    layerRef.current = L.layerGroup().addTo(map);
    layerMapRef.current = map;
    setLayerRevision((revision) => revision + 1);
  });

  useEffect(() => () => {
    if (layerRef.current) layerMapRef.current?.removeLayer(layerRef.current);
    layerRef.current = null;
    layerMapRef.current = null;
  }, [options.mapRef]);

  useEffect(() => {
    const map = options.mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer || layerRevision === 0) return;
    if (!options.showAnchors) {
      layer.clearLayers();
      options.onAnchorStatus?.("");
      return;
    }
    if (map.getZoom() < ANCHOR_MIN_ZOOM) {
      layer.clearLayers();
      options.onAnchorStatus?.(options.t("zoomInToSee", { noun: options.t("nounAnchors") }));
      return;
    }
    const controller = new AbortController();
    fetchAnchors({ bboxLonLat: bboxLonLatParam(map.getBounds()) }, controller.signal)
      .then((fc) => {
        renderAnchors(layer, fc);
        options.onAnchorStatus?.(options.t("anchorsCount", { n: fc.features.length }));
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        layer.clearLayers();
        const message = options.t("anchorError", { detail: error instanceof Error ? error.message : String(error) });
        options.onAnchorStatus?.(message);
        options.onError?.(message);
      });
    return () => controller.abort();
  }, [
    options.mapRef,
    options.onAnchorStatus,
    options.onError,
    options.showAnchors,
    options.t,
    options.viewportRevision,
    layerRevision,
  ]);
}
