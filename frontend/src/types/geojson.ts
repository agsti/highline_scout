export type Position = [number, number];

export interface PointGeometry {
  type: "Point";
  coordinates: Position;
}

export interface PolygonGeometry {
  type: "Polygon";
  coordinates: Position[][];
}

export interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: Position[][][];
}

export interface Feature<G, P> {
  type: "Feature";
  geometry: G;
  properties: P;
}

export interface FeatureCollection<F extends Feature<unknown, unknown>> {
  type: "FeatureCollection";
  features: F[];
}
