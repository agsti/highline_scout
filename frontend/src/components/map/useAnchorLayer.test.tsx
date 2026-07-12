import L from "leaflet";
import { render } from "@testing-library/react";
import { useRef, type MutableRefObject } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAnchors } from "@/lib/api";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { ANCHOR_MIN_ZOOM } from "@/lib/map-style";
import { useAnchorLayer } from "./useAnchorLayer";

const mocks = vi.hoisted(() => ({
  anchorLayer: { addTo: vi.fn(), clearLayers: vi.fn() },
  fetchAnchors: vi.fn(),
  layerGroup: vi.fn(),
  removeLayer: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ fetchAnchors: mocks.fetchAnchors }));
vi.mock("leaflet", () => ({ default: { layerGroup: mocks.layerGroup } }));
vi.mock("./leafletLayers", () => ({ renderAnchors: vi.fn() }));

const getZoom = vi.fn(() => ANCHOR_MIN_ZOOM);
const map = {
  getBounds: () => ({ getEast: () => 3, getNorth: () => 4, getSouth: () => 2, getWest: () => 1 }),
  getZoom,
  removeLayer: mocks.removeLayer,
} as unknown as L.Map;
const onAnchorStatus = vi.fn();

function AnchorHarness({ showAnchors, providedMapRef }: { showAnchors: boolean; providedMapRef?: MutableRefObject<L.Map | null> }) {
  const fallbackMapRef = useRef<L.Map | null>(map);
  const { t } = useI18n();
  useAnchorLayer({ mapRef: providedMapRef ?? fallbackMapRef, viewportRevision: 0, showAnchors, t, onAnchorStatus });
  return null;
}

function renderHarness(showAnchors: boolean) {
  return render(<I18nProvider><AnchorHarness showAnchors={showAnchors} /></I18nProvider>);
}

describe("useAnchorLayer", () => {
  beforeEach(() => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: { getItem: vi.fn(() => "ca"), setItem: vi.fn() },
    });
    mocks.fetchAnchors.mockReset().mockResolvedValue({ type: "FeatureCollection", features: [] });
    mocks.anchorLayer.addTo.mockReset().mockReturnValue(mocks.anchorLayer);
    mocks.anchorLayer.clearLayers.mockReset();
    mocks.layerGroup.mockReset().mockReturnValue(mocks.anchorLayer);
    mocks.removeLayer.mockReset();
    getZoom.mockReset().mockReturnValue(ANCHOR_MIN_ZOOM);
    onAnchorStatus.mockReset();
  });

  it("clears anchors and skips the request when disabled", () => {
    renderHarness(false);

    expect(mocks.anchorLayer.clearLayers).toHaveBeenCalledTimes(1);
    expect(fetchAnchors).not.toHaveBeenCalled();
  });

  it("shows zoom guidance instead of requesting anchors below ANCHOR_MIN_ZOOM", () => {
    getZoom.mockReturnValue(ANCHOR_MIN_ZOOM - 1);
    renderHarness(true);

    expect(fetchAnchors).not.toHaveBeenCalled();
    expect(onAnchorStatus).toHaveBeenCalledWith("amplia per veure ancoratges");
  });
});
