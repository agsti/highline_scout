import L from "leaflet";
import { act, render, waitFor } from "@testing-library/react";
import { useRef, type MutableRefObject } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchRestrictions } from "@/lib/api";
import { I18nProvider, useI18n } from "@/lib/i18n";
import type { RestrictionFeatureCollection, RestrictionLayerMeta } from "@/types/highliner";
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
const onFeaturesChange = vi.fn();
const restrictionLayers: RestrictionLayerMeta[] = [
  { id: "zepa", label: "ZEPA", tooltip: "tooltip", highlight: "tooltip", color: "#0a0" },
];

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

function RestrictionHarness({
  enabledRestrictions,
  viewportRevision = 0,
  providedMapRef,
}: {
  enabledRestrictions: string[];
  viewportRevision?: number;
  providedMapRef?: MutableRefObject<L.Map | null>;
}) {
  const fallbackMapRef = useRef<L.Map | null>(map);
  const { t } = useI18n();
  useRestrictionLayer({
    mapRef: providedMapRef ?? fallbackMapRef,
    viewportRevision,
    enabledRestrictions,
    restrictionLayers,
    t,
    onFeaturesChange,
    onRestrictionStatus,
    onError,
  });
  return null;
}

function renderHarness(enabledRestrictions: string[], viewportRevision = 0) {
  return render(
    <I18nProvider><RestrictionHarness enabledRestrictions={enabledRestrictions} viewportRevision={viewportRevision} /></I18nProvider>,
  );
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
    onFeaturesChange.mockReset();
  });

  it("clears restrictions and skips the request when none are selected", () => {
    renderHarness([]);

    expect(mocks.restrictionLayer.clearLayers).toHaveBeenCalledTimes(1);
    expect(fetchRestrictions).not.toHaveBeenCalled();
    expect(onFeaturesChange).toHaveBeenCalledWith({ type: "FeatureCollection", features: [] });
  });

  it("publishes the complete successful restriction collection", async () => {
    const collection: RestrictionFeatureCollection = {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [[[1, 2], [1, 3], [2, 3], [1, 2]]] },
        properties: { layer: "zepa" },
      }],
    };
    mocks.fetchRestrictions.mockResolvedValue(collection);

    renderHarness(["zepa"]);

    await waitFor(() => expect(onFeaturesChange).toHaveBeenCalledWith(collection));
  });

  it("clears and publishes empty restrictions before a replacement request resolves", async () => {
    const initial: RestrictionFeatureCollection = {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [[[1, 2], [1, 3], [2, 3], [1, 2]]] },
        properties: { layer: "zepa" },
      }],
    };
    const replacement = deferred<RestrictionFeatureCollection>();
    mocks.fetchRestrictions.mockResolvedValueOnce(initial).mockReturnValueOnce(replacement.promise);
    const view = renderHarness(["zepa"]);
    await waitFor(() => expect(onFeaturesChange).toHaveBeenCalledWith(initial));
    onFeaturesChange.mockClear();
    mocks.restrictionLayer.clearLayers.mockClear();

    view.rerender(
      <I18nProvider><RestrictionHarness enabledRestrictions={["zepa"]} viewportRevision={1} /></I18nProvider>,
    );

    await waitFor(() => expect(mocks.restrictionLayer.clearLayers).toHaveBeenCalledTimes(1));
    expect(onFeaturesChange).toHaveBeenCalledWith({ type: "FeatureCollection", features: [] });
    await act(async () => replacement.resolve(initial));
  });

  it("turns a 413 response into localized zoom guidance", async () => {
    mocks.fetchRestrictions.mockRejectedValue(new ApiError(413, "too many"));
    renderHarness(["zepa"]);

    await waitFor(() => expect(onRestrictionStatus).toHaveBeenCalledWith("amplia per veure espais protegits"));
    expect(onFeaturesChange).toHaveBeenCalledWith({ type: "FeatureCollection", features: [] });
    expect(onError).not.toHaveBeenCalled();
  });

  it("publishes an empty collection after a failed restriction request", async () => {
    mocks.fetchRestrictions.mockRejectedValue(new Error("offline"));
    renderHarness(["zepa"]);

    await waitFor(() => expect(onFeaturesChange).toHaveBeenCalledWith({ type: "FeatureCollection", features: [] }));
  });
});
