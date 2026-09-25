import "maplibre-gl/dist/maplibre-gl.css";
import maplibregl, { type GeoJSONSource, type LngLatBoundsLike } from "maplibre-gl";
import { Layers } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { BENIN_BOUNDS, type LngLat } from "../lib/geometry";
import { type BaseLayer, buildStyle, PARCEL_COLOR, prepareBasemap } from "../lib/map";
import { useOnline } from "../lib/useOnline";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export interface Position {
  lngLat: LngLat;
  accuracy: number;
}

interface Props {
  parcels?: GeoJSON.FeatureCollection;
  /** Points colorés par leur propriété « color » (alertes sanitaires). */
  points?: GeoJSON.FeatureCollection;
  draft?: LngLat[];
  position?: Position | null;
  fitBounds?: [LngLat, LngLat] | null;
  onMapClick?: (p: LngLat) => void;
  onParcelClick?: (id: string) => void;
  onViewChange?: (bbox: [number, number, number, number]) => void;
  className?: string;
  label?: string;
}

function circle([lon, lat]: LngLat, radiusM: number): GeoJSON.Feature {
  const pts: LngLat[] = [];
  for (let i = 0; i <= 32; i++) {
    const a = (i / 32) * 2 * Math.PI;
    pts.push([lon + (radiusM * Math.cos(a)) / (111_320 * Math.cos((lat * Math.PI) / 180)), lat + (radiusM * Math.sin(a)) / 110_540]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [pts] } };
}

function draftData(points: LngLat[]): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = points.map((p, i) => ({ type: "Feature", properties: { n: i + 1 }, geometry: { type: "Point", coordinates: p } }));
  if (points.length >= 3) features.unshift({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[...points, points[0]]] } });
  else if (points.length === 2) features.unshift({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: points } });
  return { type: "FeatureCollection", features };
}

/** Un point au centre de chaque parcelle : à l'échelle du pays, un champ d'un hectare fait moins d'un pixel. */
function centroids(fc: GeoJSON.FeatureCollection | undefined): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const f of fc?.features ?? []) {
    const ring = (f.geometry as GeoJSON.Polygon).coordinates?.[0];
    if (!ring?.length) continue;
    const n = ring.length - 1 || 1;
    const c = ring.slice(0, n).reduce((acc, p) => [acc[0] + p[0] / n, acc[1] + p[1] / n], [0, 0]);
    features.push({ type: "Feature", properties: f.properties, geometry: { type: "Point", coordinates: c } });
  }
  return { type: "FeatureCollection", features };
}

const POINTS_UNTIL_ZOOM = 12;

/** Couches de l'application, ajoutées au-dessus du fond (plan ou satellite). */
function addOverlays(map: maplibregl.Map) {
  map.addSource("parcels", { type: "geojson", data: EMPTY });
  map.addSource("parcels-points", { type: "geojson", data: EMPTY });
  map.addSource("draft", { type: "geojson", data: EMPTY });
  map.addSource("points", { type: "geojson", data: EMPTY });
  map.addSource("position", { type: "geojson", data: EMPTY });
  map.addLayer({ id: "parcels-fill", type: "fill", source: "parcels", minzoom: POINTS_UNTIL_ZOOM - 1, paint: { "fill-color": PARCEL_COLOR, "fill-opacity": 0.28 } });
  map.addLayer({ id: "parcels-line", type: "line", source: "parcels", minzoom: POINTS_UNTIL_ZOOM - 1, paint: { "line-color": PARCEL_COLOR, "line-width": 2.5 } });
  map.addLayer({ id: "parcels-dots", type: "circle", source: "parcels-points", maxzoom: POINTS_UNTIL_ZOOM,
                 paint: { "circle-color": PARCEL_COLOR, "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 3.5, 11, 6], "circle-stroke-color": "#fff", "circle-stroke-width": 1 } });
  map.addLayer({ id: "draft-fill", type: "fill", source: "draft", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": "#1d4ed8", "fill-opacity": 0.18 } });
  map.addLayer({ id: "draft-line", type: "line", source: "draft", filter: ["!=", ["geometry-type"], "Point"], paint: { "line-color": "#1d4ed8", "line-width": 3, "line-dasharray": [2, 1] } });
  map.addLayer({ id: "draft-points", type: "circle", source: "draft", filter: ["==", ["geometry-type"], "Point"],
                 paint: { "circle-radius": 6, "circle-color": "#1d4ed8", "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
  map.addLayer({ id: "points", type: "circle", source: "points",
                 paint: { "circle-color": ["match", ["get", "alert_color"], "red", "#dc2626", "orange", "#ea580c", "yellow", "#ca8a04", "green", "#047857", "#525252"],
                          "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 4, 12, 7], "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } });
  map.addLayer({ id: "position-accuracy", type: "fill", source: "position", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": "#0ea5e9", "fill-opacity": 0.15 } });
  map.addLayer({ id: "position-dot", type: "circle", source: "position", filter: ["==", ["geometry-type"], "Point"],
                 paint: { "circle-radius": 8, "circle-color": "#0284c7", "circle-stroke-color": "#fff", "circle-stroke-width": 3 } });
}

export function MapView({ parcels, points, draft, position, fitBounds, onMapClick, onParcelClick, onViewChange, className = "h-80", label = "Carte" }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [hasBasemap, setHasBasemap] = useState<boolean | null>(null);
  const [base, setBase] = useState<BaseLayer>("plan");
  const online = useOnline();
  const handlers = useRef({ onMapClick, onParcelClick, onViewChange });
  handlers.current = { onMapClick, onParcelClick, onViewChange };
  const data = useRef({ parcels, points, draft, position });
  data.current = { parcels, points, draft, position };

  useEffect(() => {
    let cancelled = false;
    prepareBasemap().then((ok) => !cancelled && setHasBasemap(ok));
    return () => {
      cancelled = true;
    };
  }, []);

  const pushData = () => {
    const map = mapRef.current;
    if (!map?.getSource("parcels")) return;
    (map.getSource("parcels") as GeoJSONSource).setData(data.current.parcels ?? EMPTY);
    (map.getSource("parcels-points") as GeoJSONSource).setData(centroids(data.current.parcels));
    (map.getSource("draft") as GeoJSONSource).setData(draftData(data.current.draft ?? []));
    (map.getSource("points") as GeoJSONSource).setData(data.current.points ?? EMPTY);
    const pos = data.current.position;
    (map.getSource("position") as GeoJSONSource).setData(
      pos ? { type: "FeatureCollection", features: [circle(pos.lngLat, pos.accuracy), { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: pos.lngLat } }] } : EMPTY,
    );
  };

  // Création de la carte
  useEffect(() => {
    if (hasBasemap === null || !container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: buildStyle("plan", hasBasemap),
      bounds: BENIN_BOUNDS as LngLatBoundsLike,
      attributionControl: { compact: true },
      maxZoom: 19,
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    map.on("style.load", () => {
      addOverlays(map);
      pushData();
      setReady(true);
    });
    map.on("click", (e) => handlers.current.onMapClick?.([e.lngLat.lng, e.lngLat.lat]));
    for (const layer of ["parcels-fill", "parcels-dots"]) {
      map.on("click", layer, (e) => {
        const id = e.features?.[0]?.properties?.id;
        if (id) handlers.current.onParcelClick?.(String(id));
      });
      map.on("mouseenter", layer, () => handlers.current.onParcelClick && (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }
    map.on("moveend", () => {
      const b = map.getBounds();
      handlers.current.onViewChange?.([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
    });
    return () => {
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, [hasBasemap]);

  // Changement de fond (les couches de l'application sont rajoutées au rechargement du style)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || hasBasemap === null || !ready) return;
    setReady(false);
    map.setStyle(buildStyle(base, hasBasemap));
  }, [base]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (ready) pushData();
  }, [ready, parcels, points, draft, position]); // eslint-disable-line react-hooks/exhaustive-deps

  const fitKey = fitBounds ? fitBounds.flat().map((v) => v.toFixed(5)).join(",") : "";
  useEffect(() => {
    if (ready && fitBounds) mapRef.current?.fitBounds(fitBounds as LngLatBoundsLike, { padding: 40, maxZoom: 17, duration: 0 });
  }, [ready, fitKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const satelliteAvailable = online;
  return (
    <div className={`relative rounded-lg overflow-hidden border border-neutral-200 bg-[#eef0ea] ${className}`}>
      {/* w-full h-full : MapLibre impose position:relative au conteneur (un positionnement absolu serait écrasé) */}
      <div ref={container} className="w-full h-full" role="region" aria-label={label} />
      {satelliteAvailable && (
        <div className="absolute top-2 right-2 z-10 flex rounded border border-neutral-300 bg-white shadow-sm overflow-hidden text-sm font-semibold">
          <Layers className="w-4 h-4 m-2 text-neutral-500" aria-hidden />
          {(["plan", "satellite"] as const).map((b) => (
            <button type="button" key={b} onClick={() => setBase(b)} aria-pressed={base === b}
                    className={`px-3 min-h-9 cursor-pointer ${base === b ? "bg-emerald-800 text-white" : "text-neutral-700 hover:bg-neutral-50"}`}>
              {b === "plan" ? "Plan (OSM)" : "Satellite"}
            </button>
          ))}
        </div>
      )}
      {hasBasemap === false && !online && (
        <p className="absolute bottom-2 left-2 z-10 max-w-[70%] px-2 py-1 rounded bg-white/90 text-xs text-neutral-700 border border-neutral-200">
          Mode hors-ligne : fond de carte non téléchargé. Seules les parcelles locales sont affichées.
        </p>
      )}
    </div>
  );
}
