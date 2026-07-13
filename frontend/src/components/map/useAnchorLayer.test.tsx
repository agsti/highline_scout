import L from "leaflet";
import { act, render, waitFor } from "@testing-library/react";
import { useRef, type MutableRefObject } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAnchors } from "@/lib/api";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { ANCHOR_MIN_ZOOM } from "@/lib/map-style";
import type {
  AnchorFeature,
  AnchorFeatureCollection,
  RestrictionAreaMode,
  RestrictionFeatureCollection,
} from "@/types/highliner";
import { useAnchorLayer } from "./useAnchorLayer";

const mocks = vi.hoisted(() => ({
  anchorLayer: { addTo: vi.fn(), clearLayers: vi.fn() },
  fetchAnchors: vi.fn(),
  layerGroup: vi.fn(),
  removeLayer: vi.fn(),
  renderAnchors: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ fetchAnchors: mocks.fetchAnchors }));
vi.mock("leaflet", () => ({ default: { layerGroup: mocks.layerGroup } }));
vi.mock("./leafletLayers", () => ({ renderAnchors: mocks.renderAnchors }));

const getZoom = vi.fn(() => ANCHOR_MIN_ZOOM);
const map = {
  getBounds: () => ({ getEast: () => 3, getNorth: () => 4, getSouth: () => 2, getWest: () => 1 }),
  getZoom,
  removeLayer: mocks.removeLayer,
} as unknown as L.Map;
const onAnchorStatus = vi.fn();

function AnchorHarness({
  showAnchors,
  providedMapRef,
  restrictionAreaMode = "informative",
  restrictionFeatures = { type: "FeatureCollection", features: [] },
}: {
  showAnchors: boolean;
  providedMapRef?: MutableRefObject<L.Map | null>;
  restrictionAreaMode?: RestrictionAreaMode;
  restrictionFeatures?: RestrictionFeatureCollection;
}) {
  const fallbackMapRef = useRef<L.Map | null>(map);
  const { t } = useI18n();
  useAnchorLayer({
    mapRef: providedMapRef ?? fallbackMapRef,
    viewportRevision: 0,
    showAnchors,
    t,
    onAnchorStatus,
    restrictionAreaMode,
    restrictionFeatures,
  });
  return null;
}

function renderHarness(
  showAnchors: boolean,
  props: Omit<React.ComponentProps<typeof AnchorHarness>, "showAnchors"> = {},
) {
  return render(
    <I18nProvider>
      <AnchorHarness showAnchors={showAnchors} {...props} />
    </I18nProvider>,
  );
}

const insideAnchor: AnchorFeature = {
  type: "Feature",
  geometry: { type: "Point", coordinates: [1.5, 2.5] },
  properties: { elev: 100, sectors: [] },
};
const outsideAnchor: AnchorFeature = {
  ...insideAnchor,
  geometry: { type: "Point", coordinates: [4, 5] },
};
const anchors: AnchorFeatureCollection = {
  type: "FeatureCollection",
  features: [insideAnchor, outsideAnchor],
};
const restriction: RestrictionFeatureCollection = {
  type: "FeatureCollection",
  features: [{
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [[[1, 2], [1, 3], [2, 3], [2, 2], [1, 2]]] },
    properties: { layer: "zepa" },
  }],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
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
    mocks.renderAnchors.mockReset();
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

  it("rerenders anchors excluding those inside selected restrictions", async () => {
    mocks.fetchAnchors.mockResolvedValue(anchors);
    const view = renderHarness(true);

    await waitFor(() => expect(mocks.renderAnchors).toHaveBeenLastCalledWith(
      mocks.anchorLayer,
      anchors,
    ));

    view.rerender(
      <I18nProvider>
        <AnchorHarness
          showAnchors
          restrictionAreaMode="exclude"
          restrictionFeatures={restriction}
        />
      </I18nProvider>,
    );

    await waitFor(() => expect(mocks.renderAnchors).toHaveBeenLastCalledWith(
      mocks.anchorLayer,
      { type: "FeatureCollection", features: [outsideAnchor] },
    ));
  });

  it("keeps anchors visible when exclusion has no restrictions", async () => {
    mocks.fetchAnchors.mockResolvedValue(anchors);
    renderHarness(true, { restrictionAreaMode: "exclude" });

    await waitFor(() => expect(mocks.renderAnchors).toHaveBeenLastCalledWith(
      mocks.anchorLayer,
      anchors,
    ));
  });

  it("uses the current restriction state when an anchor request resolves", async () => {
    const response = deferred<AnchorFeatureCollection>();
    mocks.fetchAnchors.mockReturnValue(response.promise);
    const view = renderHarness(true);

    view.rerender(
      <I18nProvider>
        <AnchorHarness
          showAnchors
          restrictionAreaMode="exclude"
          restrictionFeatures={restriction}
        />
      </I18nProvider>,
    );
    await act(async () => response.resolve(anchors));

    await waitFor(() => expect(mocks.renderAnchors).toHaveBeenLastCalledWith(
      mocks.anchorLayer,
      { type: "FeatureCollection", features: [outsideAnchor] },
    ));
  });
});
