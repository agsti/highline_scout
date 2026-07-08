import { describe, expect, it } from "vitest";
import type { ZoneFeature } from "@/types/highliner";
import { densityRank, tealShade, zoneKey } from "./map-style";

function zone(coords: [number, number][]): ZoneFeature {
  return {
    type: "Feature",
    geometry: { type: "Polygon", coordinates: [coords] },
    properties: {
      height_min: 30,
      height_max: 60,
      length_min: 80,
      length_max: 120,
      n_anchors: 2,
      n_pairs: 1,
    },
  };
}

describe("tealShade", () => {
  it("returns hsl color strings", () => {
    expect(tealShade(0)).toBe("hsl(168, 45%, 88%)");
    expect(tealShade(1)).toBe("hsl(184, 70%, 26%)");
  });
});

describe("densityRank", () => {
  it("ranks values across sorted density counts", () => {
    expect(densityRank(10, [10, 20, 30])).toBe(0);
    expect(densityRank(20, [10, 20, 30])).toBe(0.5);
    expect(densityRank(30, [10, 20, 30])).toBe(1);
  });

  it("averages tied ranks", () => {
    expect(densityRank(20, [10, 20, 20, 40])).toBeCloseTo(0.5);
  });
});

describe("zoneKey", () => {
  it("dedupes nearby centroid-equivalent zones", () => {
    const a = zone([
      [1, 41],
      [1.001, 41],
      [1.001, 41.001],
      [1, 41.001],
      [1, 41],
    ]);
    const b = zone([
      [1.00001, 41.00001],
      [1.00101, 41.00001],
      [1.00101, 41.00101],
      [1.00001, 41.00101],
      [1.00001, 41.00001],
    ]);
    expect(zoneKey(a)).toBe(zoneKey(b));
  });
});
