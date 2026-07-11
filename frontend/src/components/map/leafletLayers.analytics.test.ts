import type L from "leaflet";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createZoneLayer } from "./leafletLayers";
import type { ZoneFeature } from "@/types/highliner";

const captureMock = vi.fn();
vi.mock("@/lib/analytics", () => ({
  capture: (event: string, properties?: Record<string, unknown>) =>
    captureMock(event, properties),
}));

const t = ((key: string) => key) as never;

const zone: ZoneFeature = {
  type: "Feature",
  geometry: {
    type: "Polygon",
    coordinates: [[[1.8, 41.6], [1.81, 41.6], [1.81, 41.61], [1.8, 41.6]]],
  },
  properties: {
    height_min: 20,
    height_max: 45,
    length_min: 30,
    length_max: 90,
    n_anchors: 4,
    n_pairs: 3,
  },
};

// Leaflet does not run against jsdom here (see MapView.test.tsx, which mocks it
// wholesale), so drive the layer's onEachFeature hook directly with a stub.
function bindZone() {
  const handlers: Record<string, () => void> = {};
  const layer = {
    bindPopup: vi.fn(),
    on: vi.fn((event: string, handler: () => void) => {
      handlers[event] = handler;
    }),
  } as unknown as L.Layer;

  const options = createZoneLayer(t).options as L.GeoJSONOptions;
  options.onEachFeature?.(zone, layer);

  return { handlers, layer };
}

beforeEach(() => {
  captureMock.mockClear();
});

describe("createZoneLayer", () => {
  it("emits zone_opened when the popup opens", () => {
    const { handlers } = bindZone();

    handlers.popupopen();

    expect(captureMock).toHaveBeenCalledWith("zone_opened", {
      length_min: 30,
      length_max: 90,
      height_max: 45,
      n_pairs: 3,
    });
  });

  it("does not emit merely because the zone was rendered", () => {
    bindZone();

    expect(captureMock).not.toHaveBeenCalled();
  });
});
