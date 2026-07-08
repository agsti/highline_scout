import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { MapView } from "./MapView";

const leafletMocks = vi.hoisted(() => ({
  canvas: vi.fn(),
  circleMarker: vi.fn(),
  clearLayers: vi.fn(),
  createPane: vi.fn(),
  densityLayerAddData: vi.fn(),
  geoJsonAddData: vi.fn(),
  fitBounds: vi.fn(),
  geoJSON: vi.fn(),
  invalidateSize: vi.fn(),
  layerGroup: vi.fn(),
  map: vi.fn(),
  openOn: vi.fn(),
  panTo: vi.fn(),
  polygon: vi.fn(),
  popup: vi.fn(),
  remove: vi.fn(),
  setContent: vi.fn(),
  setLatLng: vi.fn(),
  on: vi.fn(),
  setView: vi.fn(),
  tileLayer: vi.fn(),
  zoneLayerAddData: vi.fn(),
  bindPopup: vi.fn(),
  bindTooltip: vi.fn(),
  domCreate: vi.fn(),
  domOn: vi.fn(),
  removeLayer: vi.fn(),
}));

const leafletState = vi.hoisted(() => ({
  bounds: {
    getWest: () => 1,
    getSouth: () => 2,
    getEast: () => 3,
    getNorth: () => 4,
  },
  center: { lat: 41.5, lng: 1.9 },
  contextmenu: null as null | ((event: { latlng: { lat: number; lng: number }; containerPoint: { x: number; y: number } }) => void),
  moveend: null as null | (() => void),
  pane: { style: { zIndex: "" } },
  zoom: 13,
}));

const apiMocks = vi.hoisted(() => ({
  fetchAnchors: vi.fn(),
  fetchDensity: vi.fn(),
  fetchRestrictions: vi.fn(),
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
  fetchAnchors: apiMocks.fetchAnchors,
  fetchDensity: apiMocks.fetchDensity,
  fetchRestrictions: apiMocks.fetchRestrictions,
  fetchZones: apiMocks.fetchZones,
}));

vi.mock("leaflet", () => {
  const map = {
    setView: leafletMocks.setView.mockReturnThis(),
    on: leafletMocks.on.mockImplementation((event: string, handler: (...args: never[]) => void) => {
      if (event === "moveend") leafletState.moveend = handler;
      if (event === "contextmenu") leafletState.contextmenu = handler as unknown as typeof leafletState.contextmenu;
    }),
    fitBounds: leafletMocks.fitBounds,
    panTo: leafletMocks.panTo,
    invalidateSize: leafletMocks.invalidateSize,
    createPane: leafletMocks.createPane,
    getPane: () => leafletState.pane,
    remove: leafletMocks.remove,
    getCenter: () => leafletState.center,
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

  const anchorLayer = {
    addTo: vi.fn().mockReturnThis(),
    clearLayers: leafletMocks.clearLayers,
  };

  const restrictionLayer = {
    addTo: vi.fn().mockReturnThis(),
    clearLayers: leafletMocks.clearLayers,
    addData: leafletMocks.geoJsonAddData,
  };

  const popupApi = {
    setLatLng: leafletMocks.setLatLng.mockReturnThis(),
    setContent: leafletMocks.setContent.mockReturnThis(),
    openOn: leafletMocks.openOn,
  };

  return {
    default: {
      DomEvent: {
        on: leafletMocks.domOn,
      },
      DomUtil: {
        create: leafletMocks.domCreate,
      },
      canvas: leafletMocks.canvas,
      circleMarker: leafletMocks.circleMarker,
      map: leafletMocks.map.mockReturnValue(map),
      layerGroup: leafletMocks.layerGroup.mockReturnValue(anchorLayer),
      polygon: leafletMocks.polygon,
      popup: leafletMocks.popup.mockReturnValue(popupApi),
      tileLayer: leafletMocks.tileLayer.mockReturnValue({
        addTo: vi.fn(),
      }),
      geoJSON: leafletMocks.geoJSON
        .mockReturnValueOnce(zoneLayer)
        .mockReturnValueOnce(densityLayer)
        .mockReturnValueOnce(restrictionLayer),
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
        showAnchors={props?.showAnchors ?? true}
        enabledRestrictions={props?.enabledRestrictions ?? []}
        restrictionLayers={props?.restrictionLayers ?? []}
        onViewportChange={props?.onViewportChange ?? vi.fn()}
        onMapStatus={props?.onMapStatus ?? vi.fn()}
        onAnchorStatus={props?.onAnchorStatus ?? vi.fn()}
        onRestrictionStatus={props?.onRestrictionStatus ?? vi.fn()}
        onViewStateChange={props?.onViewStateChange ?? vi.fn()}
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
        showAnchors={props?.showAnchors ?? true}
        enabledRestrictions={props?.enabledRestrictions ?? []}
        restrictionLayers={props?.restrictionLayers ?? []}
        onViewportChange={props?.onViewportChange ?? vi.fn()}
        onMapStatus={props?.onMapStatus ?? vi.fn()}
        onAnchorStatus={props?.onAnchorStatus ?? vi.fn()}
        onRestrictionStatus={props?.onRestrictionStatus ?? vi.fn()}
        onViewStateChange={props?.onViewStateChange ?? vi.fn()}
      />
    </I18nProvider>,
  );
}

describe("MapView", () => {
  const originalLocation = window.location;
  const originalLocalStorage = window.localStorage;
  const originalMatchMedia = window.matchMedia;

  function setMobileViewport(matches: boolean) {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  }

  beforeEach(() => {
    setMobileViewport(false);
    apiMocks.fetchDensity.mockReset();
    apiMocks.fetchAnchors.mockReset().mockResolvedValue({ type: "FeatureCollection", features: [] });
    apiMocks.fetchRestrictions.mockReset().mockResolvedValue({ type: "FeatureCollection", features: [] });
    apiMocks.fetchZones.mockReset();
    leafletMocks.canvas.mockReset().mockReturnValue({});
    leafletMocks.circleMarker.mockReset().mockImplementation(() => ({
      bindPopup: vi.fn().mockReturnThis(),
      addTo: vi.fn().mockReturnThis(),
    }));
    leafletMocks.bindPopup.mockReset();
    leafletMocks.bindTooltip.mockReset();
    leafletMocks.clearLayers.mockReset();
    leafletMocks.createPane.mockReset();
    leafletMocks.domCreate.mockReset();
    leafletMocks.domOn.mockReset();
    leafletMocks.densityLayerAddData.mockReset();
    leafletMocks.fitBounds.mockReset();
    leafletMocks.geoJsonAddData.mockReset();
    leafletMocks.geoJSON.mockReset();
    leafletMocks.invalidateSize.mockReset();
    leafletMocks.layerGroup.mockReset();
    leafletMocks.map.mockReset();
    leafletMocks.openOn.mockReset();
    leafletMocks.panTo.mockReset();
    leafletMocks.polygon.mockReset().mockImplementation(() => ({ addTo: vi.fn().mockReturnThis() }));
    leafletMocks.popup.mockReset();
    leafletMocks.remove.mockReset();
    leafletMocks.removeLayer.mockReset();
    leafletMocks.setContent.mockReset().mockReturnThis();
    leafletMocks.setLatLng.mockReset().mockReturnThis();
    leafletMocks.on.mockReset();
    leafletMocks.setView.mockReset().mockReturnThis();
    leafletMocks.tileLayer.mockReset();
    leafletMocks.zoneLayerAddData.mockReset();
    leafletState.center = { lat: 41.5, lng: 1.9 };
    leafletState.contextmenu = null;
    leafletState.moveend = null;
    leafletState.pane = { style: { zIndex: "" } };
    leafletState.zoom = 13;
    let zoneOnEachFeature: ((feature: unknown, layer: { bindPopup: (html: string) => void }) => void) | null = null;
    let densityOnEachFeature: ((feature: unknown, layer: { bindTooltip: (html: string) => void }) => void) | null = null;
    leafletMocks.map.mockReturnValue({
      setView: leafletMocks.setView.mockReturnThis(),
      on: leafletMocks.on.mockImplementation((event: string, handler: (...args: never[]) => void) => {
        if (event === "moveend") leafletState.moveend = handler;
        if (event === "contextmenu") leafletState.contextmenu = handler as unknown as typeof leafletState.contextmenu;
      }),
      fitBounds: leafletMocks.fitBounds,
      panTo: leafletMocks.panTo,
      invalidateSize: leafletMocks.invalidateSize,
      createPane: leafletMocks.createPane,
      getPane: () => leafletState.pane,
      removeLayer: leafletMocks.removeLayer,
      remove: leafletMocks.remove,
      getCenter: () => leafletState.center,
      getBounds: () => leafletState.bounds,
      getZoom: () => leafletState.zoom,
    });
    leafletMocks.layerGroup.mockReturnValue({
      addTo: vi.fn().mockReturnThis(),
      clearLayers: leafletMocks.clearLayers,
    });
    leafletMocks.tileLayer.mockReturnValue({ addTo: vi.fn() });
    leafletMocks.domCreate.mockImplementation((tagName: string, _className?: string, container?: HTMLElement) => {
      const element =
        tagName === "a"
          ? document.createElement("a")
          : tagName === "button"
            ? document.createElement("button")
            : document.createElement("div");
      container?.appendChild(element);
      return element;
    });
    leafletMocks.domOn.mockImplementation((element: HTMLElement, event: string, handler: EventListener) => {
      element.addEventListener(event, handler);
      return element;
    });
    leafletMocks.popup.mockReturnValue({
      setLatLng: leafletMocks.setLatLng.mockReturnThis(),
      setContent: leafletMocks.setContent.mockReturnThis(),
      openOn: leafletMocks.openOn,
    });
    let geoJsonCall = 0;
    leafletMocks.geoJSON.mockImplementation((_: unknown, options?: { onEachFeature?: ((feature: unknown, layer: unknown) => void) | null }) => {
      geoJsonCall += 1;
      const isRestrictionLayer = geoJsonCall === 3;
      const isZoneLayer = geoJsonCall < 3 ? geoJsonCall === 1 : (geoJsonCall - 4) % 2 === 0;
      if (isZoneLayer && !isRestrictionLayer) {
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
      if (!isRestrictionLayer) {
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
      }
      return {
        addTo: vi.fn().mockReturnThis(),
        clearLayers: leafletMocks.clearLayers,
        addData: leafletMocks.geoJsonAddData,
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
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: originalMatchMedia,
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
          showAnchors
          enabledRestrictions={[]}
          restrictionLayers={[]}
          onViewportChange={onViewportChange}
          onMapStatus={onMapStatus}
          onAnchorStatus={vi.fn()}
          onRestrictionStatus={vi.fn()}
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
          showAnchors
          enabledRestrictions={[]}
          restrictionLayers={[]}
          onViewportChange={onViewportChange}
          onMapStatus={onMapStatus}
          onAnchorStatus={vi.fn()}
          onRestrictionStatus={vi.fn()}
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
          showAnchors
          enabledRestrictions={[]}
          restrictionLayers={[]}
          onViewportChange={onViewportChange}
          onMapStatus={onMapStatus}
          onAnchorStatus={vi.fn()}
          onRestrictionStatus={vi.fn()}
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

  it("loads anchors above the zoom threshold and reports the anchor count", async () => {
    apiMocks.fetchZones.mockResolvedValue({ type: "FeatureCollection", features: [] });
    apiMocks.fetchAnchors.mockResolvedValue({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [1.1, 2.2] },
          properties: { elev: 1200, sectors: [[10, 40, 35]] },
        },
      ],
    });

    const onAnchorStatus = vi.fn();
    renderMapView({ onAnchorStatus });

    await waitFor(() =>
      expect(apiMocks.fetchAnchors).toHaveBeenCalledWith(
        { region: "alpha", bboxLonLat: "1,2,3,4" },
        expect.any(AbortSignal),
      ),
    );
    expect(onAnchorStatus).toHaveBeenLastCalledWith("1 ancoratges");
    expect(leafletMocks.polygon).toHaveBeenCalled();
    expect(leafletMocks.circleMarker).toHaveBeenCalled();
  });

  it("shows the anchor zoom hint and skips fetching anchors below the threshold", async () => {
    leafletState.zoom = 11;
    apiMocks.fetchZones.mockResolvedValue({ type: "FeatureCollection", features: [] });

    const onAnchorStatus = vi.fn();
    renderMapView({ onAnchorStatus });

    await waitFor(() => expect(onAnchorStatus).toHaveBeenLastCalledWith("amplia per veure ancoratges"));
    expect(apiMocks.fetchAnchors).not.toHaveBeenCalled();
  });

  it("loads enabled restrictions and reports the protected-area count", async () => {
    apiMocks.fetchZones.mockResolvedValue({ type: "FeatureCollection", features: [] });
    apiMocks.fetchRestrictions.mockResolvedValue({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Polygon", coordinates: [[[1, 2], [1, 3], [2, 3], [1, 2]]] },
          properties: { layer: "pein", name: "Montseny" },
        },
      ],
    });

    const onRestrictionStatus = vi.fn();
    renderMapView({
      enabledRestrictions: ["pein"],
      restrictionLayers: [
        { id: "pein", label: "PEIN", tooltip: "tooltip", highlight: "tooltip", color: "#0a0" },
      ],
      onRestrictionStatus,
    });

    await waitFor(() =>
      expect(apiMocks.fetchRestrictions).toHaveBeenCalledWith(
        { bboxLonLat: "1,2,3,4", layers: ["pein"] },
        expect.any(AbortSignal),
      ),
    );
    expect(leafletMocks.geoJsonAddData).toHaveBeenCalledWith(
      expect.objectContaining({ type: "FeatureCollection" }),
    );
    expect(onRestrictionStatus).toHaveBeenLastCalledWith("1 espais protegits");
  });

  it("opens a React context menu with desktop and mobile presentations", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    apiMocks.fetchZones.mockResolvedValue({ type: "FeatureCollection", features: [] });

    renderMapView();

    expect(leafletState.contextmenu).toBeTypeOf("function");
    act(() => {
      leafletState.contextmenu?.({
        latlng: { lat: 41.123456, lng: 2.234567 },
        containerPoint: { x: 120, y: 80 },
      });
    });

    const desktopMenu = screen.getByTestId("desktop-context-menu");
    const mobileMenu = screen.getByTestId("mobile-context-menu");

    expect(desktopMenu).toHaveClass("hidden", "md:block");
    expect(desktopMenu).toHaveStyle({ left: "120px", top: "80px" });
    expect(mobileMenu).toHaveClass("md:hidden");
    expect(within(mobileMenu).getByRole("heading", { name: "Accions d'aquest punt" })).toBeInTheDocument();

    const links = screen.getAllByRole("link", { name: "Veure a Google Maps" });
    expect(links[0]).toHaveAttribute("href", "https://www.google.com/maps?q=41.123456,2.234567");
    expect(within(mobileMenu).getByRole("link", { name: "Veure a Google Maps" })).toHaveClass("h-11", "border");
    expect(within(mobileMenu).getByRole("button", { name: "Copia l'enllaç" })).toHaveClass("h-11", "border");

    await user.click(screen.getAllByRole("button", { name: "Copia l'enllaç" })[0]);
    expect(writeText).toHaveBeenCalledWith("https://example.com/?lat=41.12346&lng=2.23457&z=13");
    expect(screen.queryByTestId("desktop-context-menu")).not.toBeInTheDocument();
    expect(leafletMocks.popup).not.toHaveBeenCalled();
  });

  it("centers and marks the selected context point on mobile", () => {
    setMobileViewport(true);
    apiMocks.fetchZones.mockResolvedValue({ type: "FeatureCollection", features: [] });

    renderMapView();

    act(() => {
      leafletState.contextmenu?.({
        latlng: { lat: 41.123456, lng: 2.234567 },
        containerPoint: { x: 120, y: 80 },
      });
    });

    expect(leafletMocks.panTo).toHaveBeenCalledWith([41.123456, 2.234567], { animate: true });
    expect(screen.getByTestId("mobile-context-point-marker")).toHaveClass("md:hidden");

    act(() => {
      leafletState.moveend?.();
    });

    expect(screen.getByTestId("mobile-context-point-marker")).toBeInTheDocument();
    expect(screen.getByTestId("mobile-context-menu")).toBeInTheDocument();
  });
});
