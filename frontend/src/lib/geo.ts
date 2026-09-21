/**
 * Display-only projection for the location plot: converts real coordinates
 * into x/y positions relative to the incident so they can be drawn.
 * It does NOT compute distances shown to the user (those come from the API)
 * and never invents a point: entries without coordinates are dropped.
 */

export interface GeoPoint {
  id: string;
  latitude: number;
  longitude: number;
}

export interface PlotPoint {
  id: string;
  /** -1..1 in the plot's horizontal direction (east positive). */
  x: number;
  /** -1..1 in the plot's vertical direction (north positive). */
  y: number;
}

const KM_PER_DEGREE_LATITUDE = 110.574;
const KM_PER_DEGREE_LONGITUDE_AT_EQUATOR = 111.32;

export interface PlotProjection {
  points: PlotPoint[];
  /** Half-width of the plotted area, in km (for the scale label). */
  extentKm: number;
}

export function projectRelativeTo(center: { latitude: number; longitude: number }, points: GeoPoint[]): PlotProjection {
  const cosLat = Math.cos((center.latitude * Math.PI) / 180);
  const offsets = points.map((p) => ({
    id: p.id,
    eastKm: (p.longitude - center.longitude) * KM_PER_DEGREE_LONGITUDE_AT_EQUATOR * cosLat,
    northKm: (p.latitude - center.latitude) * KM_PER_DEGREE_LATITUDE,
  }));
  const extentKm = Math.max(1, ...offsets.map((o) => Math.max(Math.abs(o.eastKm), Math.abs(o.northKm))));
  return {
    extentKm,
    points: offsets.map((o) => ({ id: o.id, x: o.eastKm / extentKm, y: o.northKm / extentKm })),
  };
}
