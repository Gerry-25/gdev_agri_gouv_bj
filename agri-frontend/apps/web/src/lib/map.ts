import { layers, namedFlavor } from "@protomaps/basemaps";
import maplibregl, { type StyleSpecification } from "maplibre-gl";
import { FileSource, PMTiles, Protocol } from "pmtiles";
import { offlineMapFile, PMTILES_URL } from "./offlineMap";

export type BaseLayer = "plan" | "satellite";

/** Clé Esri (compte développeur gratuit). Sans clé, la vue satellite n'est pas proposée. */
export const ESRI_TOKEN = import.meta.env.VITE_ESRI_TOKEN as string | undefined;
const ASSETS = `${window.location.origin}/map-assets`;
const OSM_ATTRIBUTION = '<a href="https://protomaps.com">Protomaps</a> © <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>';
// Mention exigée par Esri pour la couche World Imagery
const ESRI_ATTRIBUTION = "Powered by Esri · Esri, Maxar, Earthstar Geographics, and the GIS User Community";

let protocol: Protocol | null = null;
let basemap: Promise<boolean> | null = null;

/** Enregistre le protocole pmtiles:// ; utilise la copie hors ligne si elle existe. */
export function prepareBasemap(): Promise<boolean> {
  if (!basemap) {
    basemap = (async () => {
      if (!protocol) {
        protocol = new Protocol();
        maplibregl.addProtocol("pmtiles", protocol.tile);
      }
      const file = await offlineMapFile();
      if (file) {
        protocol.add(new PMTiles(new FileSource(file)));
        return true;
      }
      try {
        const res = await fetch(PMTILES_URL, { method: "HEAD" });
        return res.ok && !(res.headers.get("content-type") ?? "").includes("text/html");
      } catch {
        return false;
      }
    })();
  }
  return basemap;
}

/** À appeler après avoir téléchargé ou supprimé la carte hors ligne. */
export function resetBasemap(): void {
  basemap = null;
}

const pmtilesSourceUrl = () => `pmtiles://${new URL(PMTILES_URL, window.location.origin).href}`;

export function buildStyle(base: BaseLayer, hasBasemap: boolean): StyleSpecification {
  const style: StyleSpecification = {
    version: 8,
    glyphs: `${ASSETS}/fonts/{fontstack}/{range}.pbf`,
    sprite: `${ASSETS}/sprites/light`,
    sources: {},
    layers: [{ id: "fond", type: "background", paint: { "background-color": "#eef0ea" } }],
  };

  if (base === "satellite") {
    const satelliteUrl = ESRI_TOKEN
      ? `https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}?token=${ESRI_TOKEN}`
      : "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
    style.sources.satellite = {
      type: "raster",
      tileSize: 256,
      maxzoom: 19,
      attribution: ESRI_ATTRIBUTION,
      tiles: [satelliteUrl],
    };
    style.layers.push({ id: "satellite", type: "raster", source: "satellite" });
    if (hasBasemap) {
      style.sources.protomaps = { type: "vector", url: pmtilesSourceUrl(), attribution: OSM_ATTRIBUTION };
      style.layers.push(
        ...layers("protomaps", namedFlavor("light"), { lang: "fr" }).filter((l) => l.type === "symbol" && l.id.startsWith("places")),
      );
    }
  } else {
    // Mode Plan
    if (hasBasemap) {
      style.sources.protomaps = { type: "vector", url: pmtilesSourceUrl(), attribution: OSM_ATTRIBUTION };
      style.layers.push(...layers("protomaps", namedFlavor("light"), { lang: "fr" }));
    } else {
      // Fallback OpenStreetMap en tuiles raster standard (accessible sans clé et gratuit)
      style.sources.osm = {
        type: "raster",
        tileSize: 256,
        maxzoom: 19,
        attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
        tiles: [
          "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        ],
      };
      style.layers.push({ id: "osm-tiles", type: "raster", source: "osm" });
    }
  }

  return style;
}

/** Couleur d'une parcelle selon son statut (les couleurs d'alerte gardent leur sens). */
export const PARCEL_COLOR: maplibregl.ExpressionSpecification = [
  "case",
  ["==", ["get", "dispute_flag"], true], "#dc2626",
  ["==", ["get", "verification_status"], "verifiee"], "#047857",
  ["==", ["get", "verification_status"], "rejetee"], "#737373",
  "#d97706",
];
