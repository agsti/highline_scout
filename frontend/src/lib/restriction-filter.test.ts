import { describe, expect, it } from "vitest";
import type {
  AnchorFeature,
  AnchorFeatureCollection,
  RestrictionFeature,
  RestrictionFeatureCollection,
  ZoneFeature,
  ZoneFeatureCollection,
} from "../types/highliner";
import {
  filterAnchorsByRestrictions,
  filterZonesByRestrictions,
} from "./restriction-filter";

function square(minX: number, minY: number, maxX: number, maxY: number) {
  return [
    [minX, minY],
    [maxX, minY],
    [maxX, maxY],
    [minX, maxY],
    [minX, minY],
  ] as [number, number][];
}

function anchor(x: number, y: number): AnchorFeature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [x, y] },
    properties: { elev: 500, sectors: [] },
  };
}

function restriction(coordinates: [number, number][][]): RestrictionFeature {
  return {
    type: "Feature",
    geometry: { type: "Polygon", coordinates },
    properties: { layer: "zec" },
  };
}

function multiPolygonRestriction(
  coordinates: [number, number][][][],
): RestrictionFeature {
  return {
    type: "Feature",
    geometry: { type: "MultiPolygon", coordinates },
    properties: { layer: "zec" },
  };
}

function zone(coordinates: [number, number][][]): ZoneFeature {
  return {
    type: "Feature",
    geometry: { type: "Polygon", coordinates },
    properties: {
      height_min: 30,
      height_max: 50,
      length_min: 40,
      length_max: 60,
      n_anchors: 2,
      n_pairs: 1,
    },
  };
}

describe("restriction filters", () => {
  it("removes anchors inside restrictions while retaining anchors outside and in holes", () => {
    const restrictedAnchor = anchor(2, 2);
    const outsideAnchor = anchor(8, 8);
    const holeAnchor = anchor(5, 5);
    const anchors: AnchorFeatureCollection = {
      type: "FeatureCollection",
      features: [restrictedAnchor, outsideAnchor, holeAnchor],
    };
    const restrictions: RestrictionFeatureCollection = {
      type: "FeatureCollection",
      features: [restriction([square(0, 0, 6, 6), square(4, 4, 6, 6)])],
    };

    expect(filterAnchorsByRestrictions(anchors, restrictions).features).toEqual([
      outsideAnchor,
      holeAnchor,
    ]);
  });

  it("does not treat a point merely within a sloped edge's bounds as restricted", () => {
    const outsideAnchor = anchor(1, 2);
    const anchors: AnchorFeatureCollection = {
      type: "FeatureCollection",
      features: [outsideAnchor],
    };
    const restrictions: RestrictionFeatureCollection = {
      type: "FeatureCollection",
      features: [restriction([[[0, 0], [2, 2], [4, 0], [0, 0]]])],
    };

    expect(filterAnchorsByRestrictions(anchors, restrictions).features).toEqual([
      outsideAnchor,
    ]);
  });

  it("removes anchors inside any MultiPolygon constituent", () => {
    const inSecondPolygon = anchor(11, 11);
    const outsideAnchor = anchor(6, 6);
    const anchors: AnchorFeatureCollection = {
      type: "FeatureCollection",
      features: [inSecondPolygon, outsideAnchor],
    };
    const restrictions: RestrictionFeatureCollection = {
      type: "FeatureCollection",
      features: [multiPolygonRestriction([[square(0, 0, 2, 2)], [square(10, 10, 12, 12)]])],
    };

    expect(filterAnchorsByRestrictions(anchors, restrictions).features).toEqual([outsideAnchor]);
  });

  it("removes zones with any overlap in exclude mode", () => {
    const partlyOverlappingZone = zone([square(-1, 2, 2, 4)]);
    const enclosingZone = zone([square(-1, -1, 7, 7)]);
    const containedZone = zone([square(1, 1, 2, 2)]);
    const disjointZone = zone([square(8, 8, 10, 10)]);
    const zones: ZoneFeatureCollection = {
      type: "FeatureCollection",
      features: [partlyOverlappingZone, enclosingZone, containedZone, disjointZone],
    };
    const restrictions: RestrictionFeatureCollection = {
      type: "FeatureCollection",
      features: [restriction([square(0, 0, 6, 6)])],
    };

    expect(filterZonesByRestrictions(zones, restrictions).features).toEqual([
      disjointZone,
    ]);
  });

  it("filters zones in a non-first MultiPolygon constituent", () => {
    const inSecondPolygon = zone([square(10.5, 10.5, 11.5, 11.5)]);
    const outsideZone = zone([square(6, 6, 7, 7)]);
    const zones: ZoneFeatureCollection = {
      type: "FeatureCollection",
      features: [inSecondPolygon, outsideZone],
    };
    const restrictions: RestrictionFeatureCollection = {
      type: "FeatureCollection",
      features: [multiPolygonRestriction([[square(0, 0, 2, 2)], [square(10, 10, 12, 12)]])],
    };

    expect(filterZonesByRestrictions(zones, restrictions).features).toEqual([
      outsideZone,
    ]);
  });
});
