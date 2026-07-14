import L from "leaflet";
import { act, render, screen, waitFor } from "@testing-library/react";
import { useRef, type MutableRefObject } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchDensity, fetchZones } from "@/lib/api";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { DENSITY_MAX_ZOOM, DENSITY_TILE_MAX } from "@/lib/map-style";
import type {
  DensityFeatureCollection,
  RestrictionAreaMode,
  RestrictionFeatureCollection,
  ZoneFeature,
  ZoneFeatureCollection,
} from "@/types/highliner";
import { useZoneDensityLayer } from "./useZoneDensityLayer";

const mocks = vi.hoisted(() => ({
  densityLayer: {
    addData: vi.fn(),
    addTo: vi.fn(),
    clearLayers: vi.fn(),
  },
  fetchDensity: vi.fn(),
  fetchZones: vi.fn(),
  geoJSON: vi.fn(),
  removeLayer: vi.fn(),
  zoneLayer: {
    addData: vi.fn(),
    addTo: vi.fn(),
    clearLayers: vi.fn(),
  },
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    constructor(readonly status: number, readonly detail: string) {
      super(detail);
    }
  },
  fetchDensity: mocks.fetchDensity,
  fetchZones: mocks.fetchZones,
}));

vi.mock("leaflet", () => ({
  default: {
    geoJSON: mocks.geoJSON,
  },
}));

const getZoom = vi.fn(() => 13);
const map = {
  getBounds: () => ({
    getEast: () => 3,
    getNorth: () => 4,
    getSouth: () => 2,
    getWest: () => 1,
  }),
  getZoom,
  removeLayer: mocks.removeLayer,
} as unknown as L.Map;

function featureCollection(features: ZoneFeature[]): ZoneFeatureCollection {
  return { type: "FeatureCollection", features };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

const zoneA: ZoneFeature = {
  type: "Feature",
  geometry: { type: "Polygon", coordinates: [[[1, 2], [1, 3], [2, 3], [1, 2]]] },
  properties: { height_min: 30, height_max: 40, length_min: 80, length_max: 120, n_anchors: 2, n_pairs: 1 },
};
const zoneB: ZoneFeature = {
  ...zoneA,
  geometry: { type: "Polygon", coordinates: [[[4, 5], [4, 6], [5, 6], [4, 5]]] },
};

function Harness({
  viewportRevision = 0,
  providedMapRef,
  restrictionAreaMode = "informative",
  restrictionFeatures = { type: "FeatureCollection", features: [] },
}: {
  viewportRevision?: number;
  providedMapRef?: MutableRefObject<L.Map | null>;
  restrictionAreaMode?: RestrictionAreaMode;
  restrictionFeatures?: RestrictionFeatureCollection;
}) {
  const { lang, t } = useI18n();
  const fallbackMapRef = useRef<L.Map | null>(map);
  const mapRef = providedMapRef ?? fallbackMapRef;
  const { isLoading } = useZoneDensityLayer({
    mapRef,
    viewportRevision,
    minLen: 20,
    maxLen: 150,
    minExposure: 30,
    lang,
    t,
    restrictionAreaMode,
    restrictionFeatures,
  });
  return <output data-testid="loading">{String(isLoading)}</output>;
}

function renderHarness(viewportRevision = 0, providedMapRef?: MutableRefObject<L.Map | null>) {
  return render(
    <I18nProvider>
      <Harness viewportRevision={viewportRevision} providedMapRef={providedMapRef} />
    </I18nProvider>,
  );
}

const overlappingRestriction: RestrictionFeatureCollection = {
  type: "FeatureCollection",
  features: [{
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [[[0, 1], [0, 4], [3, 4], [0, 1]]] },
    properties: { layer: "zepa" },
  }],
};

const partlyOverlappingRestriction: RestrictionFeatureCollection = {
  type: "FeatureCollection",
  features: [{
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [[[0, 2.5], [0, 4], [1.5, 4], [1.5, 2.5], [0, 2.5]]] },
    properties: { layer: "zepa" },
  }],
};

describe("useZoneDensityLayer", () => {
  beforeEach(() => {
    mocks.fetchDensity.mockReset();
    mocks.fetchZones.mockReset().mockResolvedValue(featureCollection([]));
    mocks.zoneLayer.addTo.mockReset().mockReturnValue(mocks.zoneLayer);
    mocks.zoneLayer.addData.mockReset();
    mocks.zoneLayer.clearLayers.mockReset();
    mocks.densityLayer.addTo.mockReset().mockReturnValue(mocks.densityLayer);
    mocks.densityLayer.addData.mockReset();
    mocks.densityLayer.clearLayers.mockReset();
    mocks.removeLayer.mockReset();
    mocks.geoJSON.mockReset();
    let layerCount = 0;
    mocks.geoJSON.mockImplementation(() => (layerCount++ % 2 === 0 ? mocks.zoneLayer : mocks.densityLayer));
    getZoom.mockReset().mockReturnValue(13);
  });

  it("loads density at the density zoom and clamps the density tile zoom", async () => {
    getZoom.mockReturnValue(DENSITY_MAX_ZOOM);
    mocks.fetchDensity.mockResolvedValue({ type: "FeatureCollection", features: [] });

    renderHarness();

    await waitFor(() => expect(fetchDensity).toHaveBeenCalledWith(
      { z: DENSITY_TILE_MAX, bboxLonLat: "1,2,3,4" }, expect.any(AbortSignal),
    ));
  });

  it("loads and deduplicates zone features across viewport revisions", async () => {
    mocks.fetchZones
      .mockResolvedValueOnce(featureCollection([zoneA, zoneA]))
      .mockResolvedValueOnce(featureCollection([zoneA, zoneB]));

    const view = renderHarness(0);
    await waitFor(() => expect(mocks.zoneLayer.addData).toHaveBeenCalledWith(featureCollection([zoneA])));
    view.rerender(
      <I18nProvider>
        <Harness viewportRevision={1} />
      </I18nProvider>,
    );
    await waitFor(() => expect(mocks.zoneLayer.addData).toHaveBeenLastCalledWith(featureCollection([zoneA, zoneB])));
  });

  it("rerenders zones excluding those overlapping selected restrictions", async () => {
    mocks.fetchZones.mockResolvedValue(featureCollection([zoneA, zoneB]));
    const view = renderHarness();
    await waitFor(() => expect(mocks.zoneLayer.addData).toHaveBeenLastCalledWith(featureCollection([zoneA, zoneB])));

    view.rerender(
      <I18nProvider>
        <Harness restrictionAreaMode="exclude" restrictionFeatures={overlappingRestriction} />
      </I18nProvider>,
    );

    await waitFor(() => expect(mocks.zoneLayer.addData).toHaveBeenLastCalledWith(featureCollection([zoneB])));
  });

  it("filters a deferred zone response using the current restriction state", async () => {
    const response = deferred<ZoneFeatureCollection>();
    mocks.fetchZones.mockReturnValue(response.promise);
    const view = renderHarness();

    view.rerender(
      <I18nProvider>
        <Harness restrictionAreaMode="exclude" restrictionFeatures={overlappingRestriction} />
      </I18nProvider>,
    );
    await act(async () => response.resolve(featureCollection([zoneA, zoneB])));

    await waitFor(() => expect(mocks.zoneLayer.addData).toHaveBeenLastCalledWith(featureCollection([zoneB])));
  });

  it("keeps density data unfiltered when restrictions are excluded", async () => {
    getZoom.mockReturnValue(DENSITY_MAX_ZOOM);
    const density: DensityFeatureCollection = {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [[[1, 2], [1, 3], [2, 3], [1, 2]]] },
        properties: { n_pairs: 1, max_exposure: 30, length_min: 80, length_max: 120 },
      }],
    };
    mocks.fetchDensity.mockResolvedValue(density);
    const view = renderHarness();
    await waitFor(() => expect(mocks.densityLayer.addData).toHaveBeenLastCalledWith(density));

    view.rerender(
      <I18nProvider>
        <Harness restrictionAreaMode="exclude" restrictionFeatures={overlappingRestriction} />
      </I18nProvider>,
    );

    await waitFor(() => expect(mocks.densityLayer.addData).toHaveBeenLastCalledWith(density));
  });

  it("keeps loading visible until the current request resolves", async () => {
    const first = deferred<ZoneFeatureCollection>();
    const second = deferred<ZoneFeatureCollection>();
    mocks.fetchZones.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const view = renderHarness(0);
    view.rerender(
      <I18nProvider>
        <Harness viewportRevision={1} />
      </I18nProvider>,
    );
    await act(async () => first.resolve(featureCollection([])));
    expect(screen.getByTestId("loading")).toHaveTextContent("true");
    await act(async () => second.resolve(featureCollection([])));
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("false"));
  });

  it("recreates cached overlays when the map instance is replaced", async () => {
    mocks.fetchZones.mockResolvedValue(featureCollection([zoneA]));
    const mapRef: MutableRefObject<L.Map | null> = { current: map };
    const replacementMap = { ...map, removeLayer: vi.fn() } as unknown as L.Map;

    const view = renderHarness(0, mapRef);
    await waitFor(() => expect(mocks.zoneLayer.addData).toHaveBeenCalledWith(featureCollection([zoneA])));

    mapRef.current = replacementMap;
    view.rerender(
      <I18nProvider>
        <Harness viewportRevision={0} providedMapRef={mapRef} />
      </I18nProvider>,
    );

    await waitFor(() => expect(mocks.zoneLayer.addTo).toHaveBeenCalledTimes(2));
    expect(mocks.geoJSON).toHaveBeenCalledTimes(4);
    expect(mocks.removeLayer).toHaveBeenCalledWith(mocks.zoneLayer);
    expect(mocks.removeLayer).toHaveBeenCalledWith(mocks.densityLayer);
    expect(mocks.zoneLayer.addTo).toHaveBeenLastCalledWith(replacementMap);
    expect(mocks.densityLayer.addTo).toHaveBeenLastCalledWith(replacementMap);
    expect(mocks.zoneLayer.addData).toHaveBeenLastCalledWith(featureCollection([zoneA]));
    expect(fetchZones).toHaveBeenCalledTimes(1);
  });
});
