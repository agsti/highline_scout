import type {
  AnchorFeatureCollection,
  RestrictionFeatureCollection,
  ZoneFeatureCollection,
} from "../types/highliner";
import type { PolygonGeometry, Position } from "../types/geojson";

const EPSILON = 1e-10;

function pointInPolygon(point: Position, polygon: PolygonGeometry): boolean {
  const [exterior, ...holes] = polygon.coordinates;
  return pointInRing(point, exterior) && !holes.some((hole) => pointInRing(point, hole));
}

function pointInRing(point: Position, ring: Position[]): boolean {
  let inside = false;

  for (
    let index = 0, previous = ring.length - 1;
    index < ring.length;
    previous = index++
  ) {
    const currentPoint = ring[index];
    const previousPoint = ring[previous];
    if (pointOnSegment(point, previousPoint, currentPoint)) {
      return true;
    }

    const crossesRay =
      (currentPoint[1] > point[1]) !== (previousPoint[1] > point[1]) &&
      point[0] <
        ((previousPoint[0] - currentPoint[0]) * (point[1] - currentPoint[1])) /
          (previousPoint[1] - currentPoint[1]) +
          currentPoint[0];
    if (crossesRay) {
      inside = !inside;
    }
  }

  return inside;
}

function polygonsOverlap(first: PolygonGeometry, second: PolygonGeometry): boolean {
  const [firstExterior] = first.coordinates;
  const [secondExterior] = second.coordinates;

  return (
    ringsIntersect(firstExterior, secondExterior) ||
    firstExterior.some((point) => pointInPolygon(point, second)) ||
    secondExterior.some((point) => pointInPolygon(point, first))
  );
}

function ringsIntersect(first: Position[], second: Position[]): boolean {
  return first.some((firstPoint, index) => {
    const nextFirstPoint = first[(index + 1) % first.length];
    return second.some((secondPoint, secondIndex) =>
      segmentsIntersect(
        firstPoint,
        nextFirstPoint,
        secondPoint,
        second[(secondIndex + 1) % second.length],
      ),
    );
  });
}

function segmentsIntersect(a: Position, b: Position, c: Position, d: Position): boolean {
  const first = orientation(a, b, c);
  const second = orientation(a, b, d);
  const third = orientation(c, d, a);
  const fourth = orientation(c, d, b);

  return (
    (((first > EPSILON && second < -EPSILON) ||
      (first < -EPSILON && second > EPSILON)) &&
      ((third > EPSILON && fourth < -EPSILON) ||
        (third < -EPSILON && fourth > EPSILON))) ||
    (Math.abs(first) <= EPSILON && pointOnSegment(c, a, b)) ||
    (Math.abs(second) <= EPSILON && pointOnSegment(d, a, b)) ||
    (Math.abs(third) <= EPSILON && pointOnSegment(a, c, d)) ||
    (Math.abs(fourth) <= EPSILON && pointOnSegment(b, c, d))
  );
}

function orientation(a: Position, b: Position, point: Position): number {
  return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]);
}

function pointOnSegment(point: Position, start: Position, end: Position): boolean {
  return (
    Math.abs(orientation(start, end, point)) <= EPSILON &&
    point[0] >= Math.min(start[0], end[0]) - EPSILON &&
    point[0] <= Math.max(start[0], end[0]) + EPSILON &&
    point[1] >= Math.min(start[1], end[1]) - EPSILON &&
    point[1] <= Math.max(start[1], end[1]) + EPSILON
  );
}

export function filterAnchorsByRestrictions(
  anchors: AnchorFeatureCollection,
  restrictions: RestrictionFeatureCollection,
): AnchorFeatureCollection {
  return {
    ...anchors,
    features: anchors.features.filter(
      (anchor) =>
        !restrictions.features.some((restriction) =>
          pointInPolygon(anchor.geometry.coordinates, restriction.geometry),
        ),
    ),
  };
}

export function filterZonesByRestrictions(
  zones: ZoneFeatureCollection,
  restrictions: RestrictionFeatureCollection,
): ZoneFeatureCollection {
  return {
    ...zones,
    features: zones.features.filter(
      (zone) =>
        !restrictions.features.some((restriction) =>
          polygonsOverlap(zone.geometry, restriction.geometry),
        ),
    ),
  };
}
