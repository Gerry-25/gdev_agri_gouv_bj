/**
 * Calculs locaux pour l'aperçu pendant le relevé. Le serveur recalcule la surface officielle
 * (projection UTM 31N) : ces valeurs ne servent qu'à guider l'exploitant sur le terrain.
 */
export type LngLat = [number, number];

const M_PER_DEG_LAT = 110_540;
const mPerDegLon = (lat: number) => 111_320 * Math.cos((lat * Math.PI) / 180);

/** Distance approximative en mètres (suffisante à l'échelle d'un champ). */
export function distanceM(a: LngLat, b: LngLat): number {
  const lat = (a[1] + b[1]) / 2;
  const dx = (b[0] - a[0]) * mPerDegLon(lat);
  const dy = (b[1] - a[1]) * M_PER_DEG_LAT;
  return Math.hypot(dx, dy);
}

/** Surface d'un polygone (m²) par la formule du lacet, dans un repère local en mètres. */
export function areaM2(points: LngLat[]): number {
  if (points.length < 3) return 0;
  const lat0 = points.reduce((s, p) => s + p[1], 0) / points.length;
  const xy = points.map(([lon, lat]) => [lon * mPerDegLon(lat0), lat * M_PER_DEG_LAT]);
  let sum = 0;
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i];
    const [x2, y2] = xy[(i + 1) % xy.length];
    sum += x1 * y2 - x2 * y1;
  }
  return Math.abs(sum) / 2;
}

export function perimeterM(points: LngLat[]): number {
  if (points.length < 2) return 0;
  return points.reduce((s, p, i) => s + distanceM(p, points[(i + 1) % points.length]), 0);
}

/** Vrai si deux segments non adjacents du contour se croisent (tracé en « nœud papillon »). */
export function selfIntersects(points: LngLat[]): boolean {
  const n = points.length;
  if (n < 4) return false;
  const cross = (o: LngLat, a: LngLat, b: LngLat) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const intersect = (p1: LngLat, p2: LngLat, p3: LngLat, p4: LngLat) =>
    cross(p3, p4, p1) * cross(p3, p4, p2) < 0 && cross(p1, p2, p3) * cross(p1, p2, p4) < 0;
  for (let i = 0; i < n; i++) {
    for (let j = i + 2; j < n; j++) {
      if (i === 0 && j === n - 1) continue; // segments adjacents par la fermeture
      if (intersect(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n])) return true;
    }
  }
  return false;
}

export function bounds(points: LngLat[]): [LngLat, LngLat] | null {
  if (!points.length) return null;
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]];
}

/** Emprise de toutes les coordonnées d'une collection GeoJSON. */
export function featureBounds(fc: GeoJSON.FeatureCollection | undefined): [LngLat, LngLat] | null {
  const pts: LngLat[] = [];
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") pts.push(c as LngLat);
    else if (Array.isArray(c)) c.forEach(walk);
  };
  fc?.features.forEach((f) => walk((f.geometry as { coordinates?: unknown }).coordinates));
  return bounds(pts);
}

export const BENIN_BOUNDS: [LngLat, LngLat] = [[0.77, 6.14], [3.86, 12.42]];
export const inBenin = ([lon, lat]: LngLat) => lon >= 0.7 && lon <= 3.9 && lat >= 6.0 && lat <= 12.5;
