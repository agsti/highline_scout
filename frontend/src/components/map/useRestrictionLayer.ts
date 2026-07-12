import L from "leaflet";
import { useEffect, useRef, useState } from "react";
import { ApiError, fetchRestrictions } from "@/lib/api";
import { bboxLonLatParam } from "@/lib/geo";
import type { useI18n } from "@/lib/i18n";
import type { RestrictionLayerMeta } from "@/types/highliner";
import { createRestrictionLayer } from "./leafletLayers";

type T = ReturnType<typeof useI18n>["t"];

export function useRestrictionLayer(options: {
  mapRef: React.MutableRefObject<L.Map | null>;
  viewportRevision: number;
  enabledRestrictions: string[];
  restrictionLayers: RestrictionLayerMeta[];
  t: T;
  onRestrictionStatus?: (status: string) => void;
  onError?: (message: string) => void;
}): void {
  const layerRef = useRef<L.GeoJSON | null>(null);
  const layerMapRef = useRef<L.Map | null>(null);
  const metadataRef = useRef(new Map<string, RestrictionLayerMeta>());
  const [layerRevision, setLayerRevision] = useState(0);

  metadataRef.current = new Map(options.restrictionLayers.map((layer) => [layer.id, layer]));

  useEffect(() => {
    const map = options.mapRef.current;
    if (!map || layerMapRef.current === map) return;
    if (layerRef.current) layerMapRef.current?.removeLayer(layerRef.current);
    layerRef.current = createRestrictionLayer(() => metadataRef.current).addTo(map);
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
    if (options.enabledRestrictions.length === 0) {
      layer.clearLayers();
      options.onRestrictionStatus?.("");
      return;
    }
    const controller = new AbortController();
    fetchRestrictions(
      { bboxLonLat: bboxLonLatParam(map.getBounds()), layers: options.enabledRestrictions },
      controller.signal,
    )
      .then((fc) => {
        layer.clearLayers();
        layer.addData(fc);
        options.onRestrictionStatus?.(options.t("protectedAreasCount", { n: fc.features.length }));
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        layer.clearLayers();
        if (error instanceof ApiError && error.status === 413) {
          options.onRestrictionStatus?.(options.t("zoomInToSee", { noun: options.t("nounProtectedAreas") }));
        } else {
          const message = options.t("error", { detail: error instanceof Error ? error.message : String(error) });
          options.onRestrictionStatus?.(message);
          options.onError?.(message);
        }
      });
    return () => controller.abort();
  }, [
    options.enabledRestrictions,
    options.mapRef,
    options.onError,
    options.onRestrictionStatus,
    options.t,
    options.viewportRevision,
    layerRevision,
  ]);
}
