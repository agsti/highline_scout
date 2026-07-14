import type {
  Feature,
  FeatureCollection,
  MultiPolygonGeometry,
  PointGeometry,
  PolygonGeometry,
} from "./geojson";

export interface ZoneProperties {
  height_min: number;
  height_max: number;
  length_min: number;
  length_max: number;
  n_anchors: number;
  n_pairs: number;
}

export type ZoneFeature = Feature<PolygonGeometry, ZoneProperties>;
export type ZoneFeatureCollection = FeatureCollection<ZoneFeature>;

export interface DensityProperties {
  n_pairs: number;
  max_exposure: number;
  length_min: number | null;
  length_max: number | null;
}

export type DensityFeature = Feature<PolygonGeometry, DensityProperties>;
export type DensityFeatureCollection = FeatureCollection<DensityFeature>;

export type AnchorSector = [number, number, number];

export interface AnchorProperties {
  elev: number;
  sectors: AnchorSector[];
}

export type AnchorFeature = Feature<PointGeometry, AnchorProperties>;
export type AnchorFeatureCollection = FeatureCollection<AnchorFeature>;

export interface RestrictionLayerMeta {
  id: string;
  label: string;
  tooltip: string;
  highlight: string;
  color: string;
}

export interface RestrictionLayersResponse {
  layers: RestrictionLayerMeta[];
}

export interface RestrictionProperties {
  layer: string;
  name?: string;
}

export type RestrictionFeature = Feature<
  PolygonGeometry | MultiPolygonGeometry,
  RestrictionProperties
>;
export type RestrictionFeatureCollection = FeatureCollection<RestrictionFeature>;

export type RestrictionAreaMode = "informative" | "exclude";
