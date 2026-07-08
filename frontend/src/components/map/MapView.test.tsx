import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MapView } from "./MapView";

const leafletMocks = vi.hoisted(() => ({
  fitBounds: vi.fn(),
  invalidateSize: vi.fn(),
  remove: vi.fn(),
  on: vi.fn(),
  setView: vi.fn(),
}));

vi.mock("leaflet", () => {
  const map = {
    setView: leafletMocks.setView.mockReturnThis(),
    on: leafletMocks.on,
    fitBounds: leafletMocks.fitBounds,
    invalidateSize: leafletMocks.invalidateSize,
    remove: leafletMocks.remove,
  };

  return {
    default: {
      map: vi.fn(() => map),
      tileLayer: vi.fn(() => ({
        addTo: vi.fn(),
      })),
    },
  };
});

describe("MapView", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    leafletMocks.fitBounds.mockReset();
    leafletMocks.invalidateSize.mockReset();
    leafletMocks.remove.mockReset();
    leafletMocks.on.mockReset();
    leafletMocks.setView.mockReset().mockReturnThis();

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
  });

  it("keeps the URL view through the first selected-region update, then fits later region changes", () => {
    const onViewportChange = vi.fn();
    const { rerender } = render(<MapView regions={[]} region="" onViewportChange={onViewportChange} />);

    rerender(
      <MapView
        regions={[{ name: "alpha", bounds_lonlat: [1, 2, 3, 4] }]}
        region="alpha"
        onViewportChange={onViewportChange}
      />,
    );

    expect(leafletMocks.fitBounds).not.toHaveBeenCalled();

    rerender(
      <MapView
        regions={[
          { name: "alpha", bounds_lonlat: [1, 2, 3, 4] },
          { name: "beta", bounds_lonlat: [5, 6, 7, 8] },
        ]}
        region="beta"
        onViewportChange={onViewportChange}
      />,
    );

    expect(leafletMocks.fitBounds).toHaveBeenCalledTimes(1);
    expect(leafletMocks.fitBounds).toHaveBeenCalledWith([
      [6, 5],
      [8, 7],
    ]);
  });
});
