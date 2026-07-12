import L from "leaflet";
import { render, waitFor } from "@testing-library/react";
import { useRef, type MutableRefObject } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchRestrictions } from "@/lib/api";
import { I18nProvider, useI18n } from "@/lib/i18n";
import type { RestrictionLayerMeta } from "@/types/highliner";
import { useRestrictionLayer } from "./useRestrictionLayer";

const mocks = vi.hoisted(() => ({
  fetchRestrictions: vi.fn(),
  removeLayer: vi.fn(),
  restrictionLayer: { addData: vi.fn(), addTo: vi.fn(), clearLayers: vi.fn() },
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    constructor(readonly status: number, readonly detail: string) { super(detail); }
  },
  fetchRestrictions: mocks.fetchRestrictions,
}));
vi.mock("./leafletLayers", () => ({ createRestrictionLayer: vi.fn(() => mocks.restrictionLayer) }));

const map = {
  getBounds: () => ({ getEast: () => 3, getNorth: () => 4, getSouth: () => 2, getWest: () => 1 }),
  removeLayer: mocks.removeLayer,
} as unknown as L.Map;
const onError = vi.fn();
const onRestrictionStatus = vi.fn();
const restrictionLayers: RestrictionLayerMeta[] = [
  { id: "zepa", label: "ZEPA", tooltip: "tooltip", highlight: "tooltip", color: "#0a0" },
];

function RestrictionHarness({ enabledRestrictions, providedMapRef }: { enabledRestrictions: string[]; providedMapRef?: MutableRefObject<L.Map | null> }) {
  const fallbackMapRef = useRef<L.Map | null>(map);
  const { t } = useI18n();
  useRestrictionLayer({
    mapRef: providedMapRef ?? fallbackMapRef,
    viewportRevision: 0,
    enabledRestrictions,
    restrictionLayers,
    t,
    onRestrictionStatus,
    onError,
  });
  return null;
}

function renderHarness(enabledRestrictions: string[]) {
  return render(<I18nProvider><RestrictionHarness enabledRestrictions={enabledRestrictions} /></I18nProvider>);
}

describe("useRestrictionLayer", () => {
  beforeEach(() => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: { getItem: vi.fn(() => "ca"), setItem: vi.fn() },
    });
    mocks.fetchRestrictions.mockReset().mockResolvedValue({ type: "FeatureCollection", features: [] });
    mocks.restrictionLayer.addData.mockReset();
    mocks.restrictionLayer.addTo.mockReset().mockReturnValue(mocks.restrictionLayer);
    mocks.restrictionLayer.clearLayers.mockReset();
    mocks.removeLayer.mockReset();
    onError.mockReset();
    onRestrictionStatus.mockReset();
  });

  it("clears restrictions and skips the request when none are selected", () => {
    renderHarness([]);

    expect(mocks.restrictionLayer.clearLayers).toHaveBeenCalledTimes(1);
    expect(fetchRestrictions).not.toHaveBeenCalled();
  });

  it("turns a 413 response into localized zoom guidance", async () => {
    mocks.fetchRestrictions.mockRejectedValue(new ApiError(413, "too many"));
    renderHarness(["zepa"]);

    await waitFor(() => expect(onRestrictionStatus).toHaveBeenCalledWith("amplia per veure espais protegits"));
    expect(onError).not.toHaveBeenCalled();
  });
});
