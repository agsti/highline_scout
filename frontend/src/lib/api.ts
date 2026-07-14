import type {
  AnchorFeatureCollection,
  CountriesResponse,
  DensityFeatureCollection,
  RestrictionFeatureCollection,
  RestrictionLayerMeta,
  RestrictionLayersResponse,
  ZoneFeatureCollection,
} from "@/types/highliner";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

export interface ViewportQuery {
  bboxLonLat: string;
  country: string;
}

export interface ZoneQuery extends ViewportQuery {
  minLen: number;
  maxLen: number;
  minExposure: number;
}

export interface DensityQuery extends ViewportQuery {
  z: number;
}

export interface RestrictionsQuery {
  bboxLonLat: string;
  layers: string[];
  country: string;
}

async function parseError(response: Response): Promise<ApiError> {
  const body = await response.json().catch(() => ({}));
  const detail = typeof body.detail === "string" ? body.detail : String(response.status);
  return new ApiError(response.status, detail);
}

async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw await parseError(response);
  return response.json() as Promise<T>;
}

function query(params: Record<string, string | number>): string {
  return new URLSearchParams(
    Object.entries(params).map(([key, value]) => [key, String(value)]),
  ).toString();
}

export function fetchZones(params: ZoneQuery, signal?: AbortSignal): Promise<ZoneFeatureCollection> {
  return fetchJson(
    `/zones?${query({
      bbox_lonlat: params.bboxLonLat,
      min_len: params.minLen,
      max_len: params.maxLen,
      min_exposure: params.minExposure,
      country: params.country,
    })}`,
    signal,
  );
}

export function fetchDensity(params: DensityQuery, signal?: AbortSignal): Promise<DensityFeatureCollection> {
  return fetchJson(
    `/density?${query({
      z: params.z,
      bbox_lonlat: params.bboxLonLat,
      country: params.country,
    })}`,
    signal,
  );
}

export function fetchAnchors(params: ViewportQuery, signal?: AbortSignal): Promise<AnchorFeatureCollection> {
  return fetchJson(`/anchors?${query({ bbox_lonlat: params.bboxLonLat, country: params.country })}`, signal);
}

export async function fetchCountries(signal?: AbortSignal) {
  const response = await fetchJson<CountriesResponse>("/countries", signal);
  return response.countries;
}

export async function fetchRestrictionLayers(country: string, signal?: AbortSignal): Promise<RestrictionLayerMeta[]> {
  const response = await fetchJson<RestrictionLayersResponse>(`/restrictions/layers?${query({ country })}`, signal);
  return response.layers;
}

export function fetchRestrictions(
  params: RestrictionsQuery,
  signal?: AbortSignal,
): Promise<RestrictionFeatureCollection> {
  return fetchJson(
    `/restrictions?${query({
      bbox_lonlat: params.bboxLonLat,
      layers: params.layers.join(","),
      country: params.country,
    })}`,
    signal,
  );
}
