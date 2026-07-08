import { describe, expect, it } from "vitest";
import { bboxLonLatParam, destPoint, initialViewFromSearch, wedge } from "./geo";

describe("initialViewFromSearch", () => {
  it("returns a valid view from lat/lng/z params", () => {
    expect(initialViewFromSearch("?lat=41.6&lng=1.83&z=13")).toEqual({
      center: [41.6, 1.83],
      zoom: 13,
    });
  });

  it("returns null when any view param is missing or invalid", () => {
    expect(initialViewFromSearch("?lat=41.6&lng=1.83")).toBeNull();
    expect(initialViewFromSearch("?lat=x&lng=1.83&z=13")).toBeNull();
  });
});

describe("bboxLonLatParam", () => {
  it("serializes west,south,east,north", () => {
    expect(
      bboxLonLatParam({
        getWest: () => 1,
        getSouth: () => 2,
        getEast: () => 3,
        getNorth: () => 4,
      }),
    ).toBe("1,2,3,4");
  });
});

describe("destPoint and wedge", () => {
  it("moves north for a zero-degree bearing", () => {
    const [lat, lon] = destPoint(41, 2, 0, 100);
    expect(lat).toBeGreaterThan(41);
    expect(lon).toBeCloseTo(2, 4);
  });

  it("creates a wedge with the apex as the first point", () => {
    const points = wedge(41, 2, 10, 40, 30);
    expect(points[0]).toEqual([41, 2]);
    expect(points.length).toBeGreaterThan(3);
  });
});
