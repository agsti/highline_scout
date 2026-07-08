export interface MapViewState {
  center: [number, number];
  zoom: number;
}

export interface LatLngBoundsLike {
  getWest(): number;
  getSouth(): number;
  getEast(): number;
  getNorth(): number;
}

export function initialViewFromSearch(search: string): MapViewState | null {
  const params = new URLSearchParams(search);
  const lat = Number.parseFloat(params.get("lat") ?? "");
  const lng = Number.parseFloat(params.get("lng") ?? "");
  const zoom = Number.parseFloat(params.get("z") ?? "");
  if (Number.isFinite(lat) && Number.isFinite(lng) && Number.isFinite(zoom)) {
    return { center: [lat, lng], zoom };
  }
  return null;
}

export function bboxLonLatParam(bounds: LatLngBoundsLike): string {
  return [
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth(),
  ].join(",");
}

export function destPoint(
  lat: number,
  lon: number,
  bearingDeg: number,
  distM: number,
): [number, number] {
  const radiusM = 6_371_000;
  const d = distM / radiusM;
  const bearing = (bearingDeg * Math.PI) / 180;
  const lat1 = (lat * Math.PI) / 180;
  const lon1 = (lon * Math.PI) / 180;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(d) +
      Math.cos(lat1) * Math.sin(d) * Math.cos(bearing),
  );
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(bearing) * Math.sin(d) * Math.cos(lat1),
      Math.cos(d) - Math.sin(lat1) * Math.sin(lat2),
    );
  return [(lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI];
}

export function wedge(
  lat: number,
  lon: number,
  start: number,
  end: number,
  radiusM = 30,
): [number, number][] {
  let span = (end - start) % 360;
  if (span <= 0) {
    span += 360;
  }
  const steps = Math.max(2, Math.ceil(span / 10));
  const points: [number, number][] = [[lat, lon]];
  for (let i = 0; i <= steps; i += 1) {
    points.push(destPoint(lat, lon, start + (span * i) / steps, radiusM));
  }
  return points;
}
