import { formatNumber } from "@agri/core";
import { Crosshair, Footprints, MousePointerClick, Undo2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { MapView } from "../../components/MapView";
import { Alert, Button } from "../../components/ui";
import { areaM2, bounds, distanceM, inBenin, type LngLat, perimeterM, selfIntersects } from "../../lib/geometry";
import { useGps } from "../../lib/useGps";

export interface CapturedPoint {
  latitude: number;
  longitude: number;
  accuracy_m?: number;
}
export type CaptureMethod = "gps_walk" | "map_drawing";

const AUTO_STEP_M = 10;
const MAX_ACCURACY_M = 30;

function accuracyTone(a: number) {
  if (a <= 5) return ["bg-emerald-100 text-emerald-900 border-emerald-300", "Très bonne"];
  if (a <= 15) return ["bg-amber-50 text-amber-900 border-amber-300", "Correcte"];
  return ["bg-red-50 text-red-800 border-red-300", "Insuffisante : placez-vous à découvert"];
}

/**
 * Relevé du contour : en marchant autour du champ (GPS) ou en touchant la carte.
 * Le brouillon est sauvegardé à chaque point pour survivre à une fermeture de l'application.
 */
export function CaptureBoundary({ draftKey, onChange }: { draftKey: string; onChange: (points: CapturedPoint[], method: CaptureMethod) => void }) {
  const [method, setMethod] = useState<CaptureMethod>("gps_walk");
  const [points, setPoints] = useState<CapturedPoint[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(draftKey) ?? "[]");
    } catch {
      return [];
    }
  });
  const [walking, setWalking] = useState(false);
  const [auto, setAuto] = useState(false);
  const { position, error } = useGps(walking);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    localStorage.setItem(draftKey, JSON.stringify(points));
    onChangeRef.current(points, method);
  }, [points, method, draftKey]);

  const add = (p: CapturedPoint) => setPoints((prev) => [...prev, p]);
  const addHere = () => position && add({ latitude: position.lngLat[1], longitude: position.lngLat[0], accuracy_m: Math.round(position.accuracy * 10) / 10 });

  // Point automatique tous les 10 m parcourus, si la précision est suffisante
  useEffect(() => {
    if (!auto || !position || position.accuracy > 15) return;
    const last = points[points.length - 1];
    if (!last || distanceM([last.longitude, last.latitude], position.lngLat) >= AUTO_STEP_M) addHere();
  }, [auto, position]); // eslint-disable-line react-hooks/exhaustive-deps

  const lngLats: LngLat[] = points.map((p) => [p.longitude, p.latitude]);
  const area = areaM2(lngLats);
  const crossing = selfIntersects(lngLats);
  const outside = lngLats.some((p) => !inBenin(p));
  const [tone, toneLabel] = position ? accuracyTone(position.accuracy) : ["", ""];
  const fit = walking && position ? bounds([...lngLats, position.lngLat]) : bounds(lngLats);

  return (
    <div className="space-y-3">
      <div role="tablist" aria-label="Mode de relevé" className="grid grid-cols-2 gap-2">
        {([["gps_walk", "En marchant (GPS)", Footprints], ["map_drawing", "Sur la carte", MousePointerClick]] as const).map(([m, label, Icon]) => (
          <button type="button" key={m} role="tab" aria-selected={method === m} onClick={() => { setMethod(m); if (m === "map_drawing") setWalking(false); }}
                  className={`min-h-11 px-3 rounded border text-sm font-semibold flex items-center justify-center gap-2 cursor-pointer ${method === m ? "border-emerald-800 bg-emerald-50 text-emerald-950" : "border-neutral-300 text-neutral-700"}`}>
            <Icon className="w-4 h-4" aria-hidden /> {label}
          </button>
        ))}
      </div>

      {method === "gps_walk" ? (
        <p className="text-sm text-neutral-600">Placez-vous à un coin du champ. Ajoutez un point à chaque coin ou changement de direction, en faisant le tour. Gardez l'écran allumé.</p>
      ) : (
        <p className="text-sm text-neutral-600">Touchez la carte à chaque coin du champ, dans l'ordre. La vue satellite aide à repérer les limites.</p>
      )}

      <MapView
        className="h-[52vh] min-h-72"
        draft={lngLats}
        position={walking ? position : null}
        fitBounds={fit}
        onMapClick={method === "map_drawing" ? ([lon, lat]) => add({ latitude: lat, longitude: lon }) : undefined}
        label="Carte du relevé"
      />

      {method === "gps_walk" && (
        <div className="space-y-2">
          {!walking ? (
            <Button className="w-full" onClick={() => setWalking(true)}>
              <Crosshair className="w-4 h-4" aria-hidden /> Activer le GPS
            </Button>
          ) : (
            <>
              {error && <Alert tone="warning">{error}</Alert>}
              {position && (
                <div className={`p-2.5 rounded border text-sm flex items-center justify-between gap-2 ${tone}`} aria-live="polite">
                  <span>Précision GPS : <strong className="tabular-nums">{Math.round(position.accuracy)} m</strong></span>
                  <span className="font-semibold">{toneLabel}</span>
                </div>
              )}
              <Button className="w-full min-h-14 text-base" onClick={addHere} disabled={!position || position.accuracy > MAX_ACCURACY_M}>
                Ajouter un point ici
              </Button>
              <label className="flex items-center gap-2 text-sm text-neutral-700 min-h-11">
                <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="w-5 h-5 accent-emerald-800" />
                Ajouter un point automatiquement tous les {AUTO_STEP_M} m
              </label>
            </>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-neutral-50 border border-neutral-200 rounded text-sm">
        <span>
          <strong className="tabular-nums">{points.length}</strong> point{points.length > 1 ? "s" : ""}
          {points.length >= 3 && (
            <> · environ <strong className="tabular-nums">{formatNumber(area / 10_000, 2)} ha</strong> · périmètre {formatNumber(perimeterM(lngLats))} m</>
          )}
        </span>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setPoints((p) => p.slice(0, -1))} disabled={!points.length}>
            <Undo2 className="w-4 h-4" aria-hidden /> Annuler le dernier
          </Button>
          <Button variant="ghost" onClick={() => window.confirm("Effacer tous les points ?") && setPoints([])} disabled={!points.length}>
            Tout effacer
          </Button>
        </div>
      </div>
      {crossing && <Alert tone="error">Les côtés du contour se croisent : annulez les derniers points et suivez le tour du champ dans l'ordre.</Alert>}
      {outside && <Alert tone="error">Un point est hors du Bénin : vérifiez la position.</Alert>}
      {points.length >= 3 && area < 50 && <Alert tone="warning">Surface très petite : vérifiez que les points font bien le tour du champ.</Alert>}
    </div>
  );
}

export function captureProblems(points: CapturedPoint[]): string | null {
  const ll: LngLat[] = points.map((p) => [p.longitude, p.latitude]);
  if (points.length < 3) return "Relevez au moins 3 points.";
  if (selfIntersects(ll)) return "Les côtés du contour se croisent.";
  if (ll.some((p) => !inBenin(p))) return "Un point est hors du Bénin.";
  return null;
}
