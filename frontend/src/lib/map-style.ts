import type { ZoneFeature } from "@/types/highliner";

export const ZONE_COLOR = "hsl(184, 70%, 26%)";
export const ANCHOR_COLOR = "#1f9e8f";
export const DENSITY_MAX_ZOOM = 12;
export const DENSITY_ZOOM_OFFSET = 2;
export const DENSITY_TILE_MIN = 6;
export const DENSITY_TILE_MAX = 14;
export const ANCHOR_MIN_ZOOM = 12;
export const ANCHOR_DETAIL_LIMIT = 400;
export const ANCHOR_WEDGE_RADIUS_M = 30;
export const ZONE_DEDUP_GRID_DEG = 0.0005;

export function tealShade(value: number): string {
  const t = Math.min(Math.max(value, 0), 1);
  const h = 168 + 16 * t;
  const s = 45 + 25 * t;
  const l = 88 - 62 * t;
  return `hsl(${h}, ${s}%, ${l}%)`;
}

export function densityRank(n: number, sorted: number[]): number {
  const m = sorted.length;
  if (m <= 1) {
    return 1;
  }
  let lo = 0;
  let hi = m;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (sorted[mid] < n) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  let hiIdx = lo;
  while (hiIdx < m && sorted[hiIdx] === n) {
    hiIdx += 1;
  }
  return ((lo + hiIdx - 1) / 2) / (m - 1);
}

export function zoneKey(feature: ZoneFeature): string {
  const ring = feature.geometry.coordinates[0];
  let lon = 0;
  let lat = 0;
  for (const [x, y] of ring) {
    lon += x;
    lat += y;
  }
  lon /= ring.length;
  lat /= ring.length;
  return `${Math.round(lat / ZONE_DEDUP_GRID_DEG)}:${Math.round(lon / ZONE_DEDUP_GRID_DEG)}`;
}
