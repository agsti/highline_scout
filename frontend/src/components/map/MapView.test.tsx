import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { MapView } from "./MapView";

const leafletMocks = vi.hoisted(() => ({
  clearLayers: vi.fn(),
  densityLayerAddData: vi.fn(),
  fitBounds: vi.fn(),
  geoJSON: vi.fn(),
  invalidateSize: vi.fn(),
  map: vi.fn(),
  remove: vi.fn(),
  on: vi.fn(),
  setView: vi.fn(),
  tileLayer: vi.fn(),
  zoneLayerAddData: vi.fn(),
  bindPopup: vi.fn(),
  bindTooltip: vi.fn(),
  removeLayer: vi.fn(),
}));

const leafletState = vi.hoisted(() => ({
  bounds: {
    getWest: () => 1,
    getSouth: () => 2,
    getEast: () => 3,
    getNorth: () => 4,
  },
  moveend: null as null | (() => void),
  zoom: 13,
}));

const apiMocks = vi.hoisted(() => ({
  fetchDensity: vi.fn(),
  fetchZones: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    constructor(
      readonly status: number,
      readonly detail: string,
    ) {
      super(detail);
      this.name = "ApiError";
    }
  },
  fetchDensity: apiMocks.fetchDensity,
  fetchZones: apiMocks.fetchZones,
}));

vi.mock("leaflet", () => {
  const map = {
    setView: leafletMocks.setView.mockReturnThis(),
    on: leafletMocks.on.mockImplementation((event: string, handler: () => void) => {
      if (event === "moveend") leafletState.moveend = handler;
    }),
    fitBounds: leafletMocks.fitBounds,
    invalidateSize: leafletMocks.invalidateSize,
    remove: leafletMocks.remove,
    getBounds: () => leafletState.bounds,
    getZoom: () => leafletState.zoom,
  };

  const zoneLayer = {
    addTo: vi.fn().mockReturnThis(),
    clearLayers: leafletMocks.clearLayers,
    addData: leafletMocks.zoneLayerAddData,
    bindPopup: leafletMocks.bindPopup,
  };

  const densityLayer = {
    addTo: vi.fn().mockReturnThis(),
    clearLayers: leafletMocks.clearLayers,
    addData: leafletMocks.densityLayerAddData,
    bindTooltip: leafletMocks.bindTooltip,
  };

  return {
    default: {
      map: leafletMocks.map.mockReturnValue(map),
      tileLayer: leafletMocks.tileLayer.mockReturnValue({
        addTo: vi.fn(),
      }),
      geoJSON: leafletMocks.geoJSON
        .mockReturnValueOnce(zoneLayer)
        .mockReturnValueOnce(densityLayer),
    },
  };
});

function renderMapView(props?: Partial<React.ComponentProps<typeof MapView>>) {
  return render(
    <I18nProvider>
      <MapView
        regions={props?.regions ?? [{ name: "alpha", bounds_lonlat: [1, 2, 3, 4] }]}
        region={props?.region ?? "alpha"}
        maxLen={props?.maxLen ?? 150}
        minExposure={props?.minExposure ?? 30}
        onViewportChange={props?.onViewportChange ?? vi.fn()}
        onMapStatus={props?.onMapStatus ?? vi.fn()}
      />
    </I18nProvider>,
  );
}

function LanguageControl() {
  const { setLang } = useI18n();
  return (
    <button type="button" onClick={() => setLang("en")}>
      set english
    </button>
  );
}

function renderMapViewWithLanguageControl(props?: Partial<React.ComponentProps<typeof MapView>>) {
  return render(
    <I18nProvider>
      <LanguageControl />
      <MapView
        regions={props?.regions ?? [{ name: "alpha", bounds_lonlat: [1, 2, 3, 4] }]}
        region={props?.region ?? "alpha"}
        maxLen={props?.maxLen ?? 150}
        minExposure={props?.minExposure ?? 30}
        onViewportChange={props?.onViewportChange ?? vi.fn()}
        onMapStatus={props?.onMapStatus ?? vi.fn()}
      />
    </I18nProvider>,
  );
}

describe("MapView", () => {
  const originalLocation = window.location;
  const originalLocalStorage = window.localStorage;

  beforeEach(() => {
    apiMocks.fetchDensity.mockReset();
    apiMocks.fetchZones.mockReset();
    leafletMocks.bindPopup.mockReset();
    leafletMocks.bindTooltip.mockReset();
    leafletMocks.clearLayers.mockReset();
    leafletMocks.densityLayerAddData.mockReset();
    leafletMocks.fitBounds.mockReset();
    leafletMocks.geoJSON.mockReset();
    leafletMocks.invalidateSize.mockReset();
    leafletMocks.map.mockReset();
    leafletMocks.remove.mockReset();
    leafletMocks.removeLayer.mockReset();
    leafletMocks.on.mockReset();
    leafletMocks.setView.mockReset().mockReturnThis();
    leafletMocks.tileLayer.mockReset();
    leafletMocks.zoneLayerAddData.mockReset();
    leafletState.moveend = null;
    leafletState.zoom = 13;
    let zoneOnEachFeature: ((feature: unknown, layer: { bindPopup: (html: string) => void }) => void) | null = null;
    let densityOnEachFeature: ((feature: unknown, layer: { bindTooltip: (html: string) => void }) => void) | null = null;
    leafletMocks.map.mockReturnValue({
      setView: leafletMocks.setView.mockReturnThis(),
      on: leafletMocks.on.mockImplementation((event: string, handler: () => void) => {
        if (event === "moveend") leafletState.moveend = handler;
      }),
      fitBounds: leafletMocks.fitBounds,
      invalidateSize: leafletMocks.invalidateSize,
      removeLayer: leafletMocks.removeLayer,
      remove: leafletMocks.remove,
      getBounds: () => leafletState.bounds,
      getZoom: () => leafletState.zoom,
    });
    leafletMocks.tileLayer.mockReturnValue({ addTo: vi.fn() });
    let geoJsonCall = 0;
    leafletMocks.geoJSON.mockImplementation((_: unknown, options?: { onEachFeature?: ((feature: unknown, layer: unknown) => void) | null }) => {
      const isZoneLayer = geoJsonCall % 2 === 0;
      geoJsonCall += 1;
      if (isZoneLayer) {
        zoneOnEachFeature = (options?.onEachFeature as typeof zoneOnEachFeature) ?? null;
        return {
          addTo: vi.fn().mockReturnThis(),
          clearLayers: leafletMocks.clearLayers,
          addData: leafletMocks.zoneLayerAddData.mockImplementation((fc: { features?: unknown[] }) => {
            for (const feature of fc.features ?? []) {
              zoneOnEachFeature?.(feature, { bindPopup: leafletMocks.bindPopup });
            }
          }),
          bindPopup: leafletMocks.bindPopup,
        };
      }
      densityOnEachFeature = (options?.onEachFeature as typeof densityOnEachFeature) ?? null;
      return {
        addTo: vi.fn().mockReturnThis(),
        clearLayers: leafletMocks.clearLayers,
        addData: leafletMocks.densityLayerAddData.mockImplementation((fc: { features?: unknown[] }) => {
          for (const feature of fc.features ?? []) {
            densityOnEachFeature?.(feature, { bindTooltip: leafletMocks.bindTooltip });
          }
        }),
        bindTooltip: leafletMocks.bindTooltip,
      };
    });

    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: vi.fn((key: string) => (key === "lang" ? "ca" : null)),
        setItem: vi.fn(),
      },
    });

    Object.defineProperty(window, "location", {
      configurable: true,
      value: new URL("https://example.com/?lat=41.5&lng=1.9&z=12"),
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: originalLocalStorage,
    });
  });

  it("keeps the URL view through the first selected-region update, then fits later region changes", () => {
    const onViewportChange = vi.fn();
    const onMapStatus = vi.fn();
    const { rerender } = renderMapView({
      regions: [],
      region: "",
      onViewportChange,
      onMapStatus,
    });

    rerender(
      <I18nProvider>
        <MapView
          regions={[{ name: "alpha", bounds_lonlat: [1, 2, 3, 4] }]}
          region="alpha"
          maxLen={150}
          minExposure={30}
          onViewportChange={onViewportChange}
          onMapStatus={onMapStatus}
        />
      </I18nProvider>,
    );

    expect(leafletMocks.fitBounds).not.toHaveBeenCalled();

    rerender(
      <I18nProvider>
        <MapView
          regions={[
            { name: "alpha", bounds_lonlat: [1, 2, 3, 4] },
            { name: "beta", bounds_lonlat: [5, 6, 7, 8] },
          ]}
          region="beta"
          maxLen={150}
          minExposure={30}
          onViewportChange={onViewportChange}
          onMapStatus={onMapStatus}
        />
      </I18nProvider>,
    );

    expect(leafletMocks.fitBounds).toHaveBeenCalledTimes(1);
    expect(leafletMocks.fitBounds).toHaveBeenCalledWith([
      [6, 5],
      [8, 7],
    ]);
  });

  it("loads density cells at low zoom and reports hotspot status", async () => {
    leafletState.zoom = 12;
    apiMocks.fetchDensity.mockResolvedValue({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Polygon", coordinates: [[[1, 2], [1, 3], [2, 3], [1, 2]]] },
          properties: { n_pairs: 4, max_exposure: 55, length_min: 80, length_max: 120 },
        },
        {
          type: "Feature",
          geometry: { type: "Polygon", coordinates: [[[2, 2], [2, 3], [3, 3], [2, 2]]] },
          properties: { n_pairs: 8, max_exposure: 65, length_min: 90, length_max: 140 },
        },
      ],
    });

    const onMapStatus = vi.fn();
    renderMapView({ onMapStatus });

    await waitFor(() =>
      expect(apiMocks.fetchDensity).toHaveBeenCalledWith(
        { region: "alpha", z: 14, bboxLonLat: "1,2,3,4" },
        expect.any(AbortSignal),
      ),
    );

    expect(leafletMocks.densityLayerAddData).toHaveBeenCalledWith(
      expect.objectContaining({ type: "FeatureCollection" }),
    );
    expect(onMapStatus).toHaveBeenCalledWith("carregant punts d'interès…");
    expect(onMapStatus).toHaveBeenLastCalledWith("2 cel·les de punts d'interès (amplia per veure zones)");
    expect(screen.getByText("Probabilitat de línies")).toBeInTheDocument();
    expect(screen.getByText("baixa")).toBeInTheDocument();
    expect(screen.getByText("alta")).toBeInTheDocument();
  });

  it("loads zones at high zoom, accumulates across pans, and resets on filter changes", async () => {
    const zoneA = {
      type: "Feature" as const,
      geometry: { type: "Polygon" as const, coordinates: [[[1, 2], [1, 2.1], [1.1, 2.1], [1, 2]]] },
      properties: { height_min: 40, height_max: 55, length_min: 80, length_max: 110, n_anchors: 2, n_pairs: 1 },
    };
    const zoneB = {
      type: "Feature" as const,
      geometry: { type: "Polygon" as const, coordinates: [[[3, 4], [3, 4.1], [3.1, 4.1], [3, 4]]] },
      properties: { height_min: 60, height_max: 75, length_min: 90, length_max: 130, n_anchors: 3, n_pairs: 2 },
    };
    apiMocks.fetchZones
      .mockResolvedValueOnce({ type: "FeatureCollection", features: [zoneA, zoneA] })
      .mockResolvedValueOnce({ type: "FeatureCollection", features: [zoneB] })
      .mockResolvedValueOnce({ type: "FeatureCollection", features: [zoneB] });

    const onMapStatus = vi.fn();
    const onViewportChange = vi.fn();
    const view = renderMapView({ onMapStatus, onViewportChange });

    await waitFor(() => expect(apiMocks.fetchZones).toHaveBeenCalledTimes(1));
    expect(leafletMocks.zoneLayerAddData).toHaveBeenCalledWith({
      type: "FeatureCollection",
      features: [zoneA],
    });
    expect(onMapStatus).toHaveBeenLastCalledWith("1 zones");

    act(() => {
      leafletState.moveend?.();
    });

    await waitFor(() => expect(apiMocks.fetchZones).toHaveBeenCalledTimes(2));
    expect(onViewportChange).toHaveBeenCalledTimes(2);
    expect(leafletMocks.zoneLayerAddData).toHaveBeenLastCalledWith({
      type: "FeatureCollection",
      features: [zoneB],
    });
    expect(onMapStatus).toHaveBeenLastCalledWith("2 zones");

    view.rerender(
      <I18nProvider>
        <MapView
          regions={[{ name: "alpha", bounds_lonlat: [1, 2, 3, 4] }]}
          region="alpha"
          maxLen={200}
          minExposure={30}
          onViewportChange={onViewportChange}
          onMapStatus={onMapStatus}
        />
      </I18nProvider>,
    );

    await waitFor(() => expect(apiMocks.fetchZones).toHaveBeenCalledTimes(3));
    expect(leafletMocks.clearLayers).toHaveBeenCalled();
    expect(onMapStatus).toHaveBeenLastCalledWith("1 zones");
  });

  it("rebinds cached zone popups in the new language without refetching zones", async () => {
    apiMocks.fetchZones.mockResolvedValue({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Polygon", coordinates: [[[1, 2], [1, 3], [2, 3], [1, 2]]] },
          properties: {
            height_min: 30,
            height_max: 40,
            length_min: 80,
            length_max: 120,
            n_anchors: 2,
            n_pairs: 1,
          },
        },
      ],
    });

    renderMapViewWithLanguageControl();

    await waitFor(() => expect(apiMocks.fetchZones).toHaveBeenCalledTimes(1));
    expect(leafletMocks.bindPopup).toHaveBeenCalledWith("alçada 30–40 m<br>longitud 80–120 m<br>2 ancoratges · 1 línies");

    await act(async () => {
      screen.getByRole("button", { name: "set english" }).click();
    });

    await waitFor(() =>
      expect(leafletMocks.bindPopup).toHaveBeenCalledWith("height 30–40 m<br>length 80–120 m<br>2 anchors · 1 lines"),
    );
    expect(apiMocks.fetchZones).toHaveBeenCalledTimes(1);
  });

  it("rebinds cached density tooltips in the new language and hides the legend outside density mode", async () => {
    leafletState.zoom = 12;
    apiMocks.fetchDensity.mockResolvedValue({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Polygon", coordinates: [[[1, 2], [1, 3], [2, 3], [1, 2]]] },
          properties: { n_pairs: 4, max_exposure: 55, length_min: 80, length_max: 120 },
        },
      ],
    });

    renderMapViewWithLanguageControl();

    await waitFor(() => expect(apiMocks.fetchDensity).toHaveBeenCalledTimes(1));
    expect(leafletMocks.bindTooltip).toHaveBeenCalledWith("4 línies candidates · fins a 55 m · 80–120 m de llarg");

    await act(async () => {
      screen.getByRole("button", { name: "set english" }).click();
    });

    await waitFor(() =>
      expect(leafletMocks.bindTooltip).toHaveBeenCalledWith("4 candidate lines · up to 55 m · 80–120 m long"),
    );
    expect(apiMocks.fetchDensity).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Line chance")).toBeInTheDocument();

    leafletState.zoom = 13;
    await act(async () => {
      leafletState.moveend?.();
    });

    await waitFor(() => expect(screen.queryByText("Line chance")).not.toBeInTheDocument());
  });
});
