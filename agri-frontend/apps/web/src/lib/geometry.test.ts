import { describe, expect, it } from "vitest";
import { areaM2, distanceM, perimeterM, selfIntersects, type LngLat } from "./geometry";

// Carré d'environ 100 m de côté près de Dangbo (même valeur que les tests du backend : 0,99 ha)
const d = 0.0009;
const square: LngLat[] = [[2.55, 6.58], [2.55 + d, 6.58], [2.55 + d, 6.58 + d], [2.55, 6.58 + d]];

describe("géométrie locale", () => {
  it("calcule la surface d'un carré d'environ un hectare", () => {
    expect(areaM2(square) / 10_000).toBeCloseTo(0.99, 1);
  });
  it("calcule distances et périmètre", () => {
    expect(distanceM(square[0], square[1])).toBeGreaterThan(95);
    expect(perimeterM(square)).toBeGreaterThan(390);
  });
  it("détecte un contour dont les côtés se croisent", () => {
    expect(selfIntersects(square)).toBe(false);
    expect(selfIntersects([square[0], square[2], square[1], square[3]])).toBe(true);
  });
  it("ignore les contours incomplets", () => {
    expect(areaM2(square.slice(0, 2))).toBe(0);
  });
});
