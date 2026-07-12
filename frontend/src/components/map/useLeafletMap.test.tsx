import { act, render, screen } from "@testing-library/react";
import L from "leaflet";
import { useCallback, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLeafletMap } from "./useLeafletMap";

const leafletMocks = vi.hoisted(() => ({
  createPane: vi.fn(),
  map: vi.fn(),
  remove: vi.fn(),
  setView: vi.fn(),
  tileLayer: vi.fn(),
}));

const leafletState = vi.hoisted(() => ({
  center: { lat: 41.5, lng: 1.9 },
  moveend: null as null | (() => void),
  pane: { style: { zIndex: "" } },
  zoom: 13,
}));

vi.mock("leaflet", () => {
  const map = {
    createPane: leafletMocks.createPane,
    getCenter: () => leafletState.center,
    getBounds: () => ({ getWest: () => 1, getSouth: () => 2, getEast: () => 3, getNorth: () => 4 }),
    getPane: () => leafletState.pane,
    getZoom: () => leafletState.zoom,
    on: vi.fn((event: string, handler: () => void) => {
      if (event === "moveend") leafletState.moveend = handler;
    }),
    remove: leafletMocks.remove,
    setView: leafletMocks.setView.mockReturnThis(),
  };

  return {
    default: {
      map: leafletMocks.map.mockReturnValue(map),
      tileLayer: leafletMocks.tileLayer.mockReturnValue({ addTo: vi.fn() }),
    },
  };
});

function Harness({ onViewportChange }: { onViewportChange: (map: L.Map) => void }) {
  const [element, setElement] = useState<HTMLDivElement | null>(null);
  const setMapElement = useCallback((node: HTMLDivElement | null) => setElement(node), []);
  const { viewportRevision } = useLeafletMap({
    element,
    t: ((key: string) => key) as never,
    lang: "ca",
    onViewportChange,
    onMapSettled: vi.fn(),
    onContextMenu: vi.fn(),
  });

  return (
    <>
      <div ref={setMapElement} />
      <output data-testid="viewport-revision">{viewportRevision}</output>
    </>
  );
}

describe("useLeafletMap", () => {
  beforeEach(() => {
    leafletMocks.createPane.mockReset();
    leafletMocks.map.mockClear();
    leafletMocks.remove.mockReset();
    leafletMocks.setView.mockReset().mockReturnThis();
    leafletMocks.tileLayer.mockReset().mockReturnValue({ addTo: vi.fn() });
    leafletState.center = { lat: 41.5, lng: 1.9 };
    leafletState.moveend = null;
    leafletState.pane = { style: { zIndex: "" } };
    leafletState.zoom = 13;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("creates the base map once, publishes the initial viewport, and disposes it", () => {
    const onViewportChange = vi.fn();
    const { unmount } = render(<Harness onViewportChange={onViewportChange} />);

    expect(leafletMocks.map).toHaveBeenCalledTimes(1);
    expect(onViewportChange).toHaveBeenCalledWith(expect.objectContaining({ getBounds: expect.any(Function) }));

    unmount();
    expect(leafletMocks.remove).toHaveBeenCalledTimes(1);
  });

  it("increments the viewport revision and publishes state after moveend", () => {
    const onViewportChange = vi.fn();
    render(<Harness onViewportChange={onViewportChange} />);

    act(() => leafletState.moveend?.());

    expect(screen.getByTestId("viewport-revision")).toHaveTextContent("1");
    expect(onViewportChange).toHaveBeenCalledTimes(2);
  });
});
