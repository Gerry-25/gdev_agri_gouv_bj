import { api } from "@agri/core";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle, CloudSun, RefreshCw, ShieldAlert } from "lucide-react";
import type { Weather } from "../lib/queries";
import { Card, CardHeader, Loading } from "./ui";

const TONE = {
  green: { box: "bg-emerald-50 border-emerald-200 text-emerald-950", Icon: CheckCircle, icon: "text-emerald-700" },
  orange: { box: "bg-amber-50 border-amber-200 text-amber-950", Icon: AlertTriangle, icon: "text-amber-700" },
  red: { box: "bg-red-50 border-red-200 text-red-950", Icon: ShieldAlert, icon: "text-red-700" },
};
const DAY = new Intl.DateTimeFormat("fr-FR", { weekday: "short" });

/** Météo agricole réelle (Open-Meteo via l'API) : alerte simple, conseil de semis et de traitement. */
export function WeatherWidget({ landId, commune }: { landId?: string; commune?: string | null }) {
  const q = useQuery({
    queryKey: ["weather", landId ?? commune],
    enabled: !!(landId || commune),
    staleTime: 30 * 60_000,
    queryFn: async () => {
      const res = landId
        ? await api.GET("/api/v1/monitoring/weather/land/{land_id}", { params: { path: { land_id: landId } } })
        : await api.GET("/api/v1/monitoring/weather-alerts/{commune}", { params: { path: { commune: commune! } } });
      if (res.error) throw new Error("Météo indisponible");
      return res.data as unknown as Weather;
    },
  });
  const w = q.data;
  const tone = w ? TONE[w.summary.color] : null;

  return (
    <Card>
      <CardHeader
        icon={CloudSun}
        title={`Météo agricole${w?.commune ? ` · ${w.commune}` : ""}`}
        action={
          <button type="button" onClick={() => q.refetch()} disabled={q.isFetching} aria-label="Actualiser la météo" className="p-2 text-neutral-500 hover:text-neutral-800 rounded cursor-pointer">
            <RefreshCw className={`w-4 h-4 ${q.isFetching ? "animate-spin" : ""}`} aria-hidden />
          </button>
        }
      />
      {!landId && !commune && <p className="text-sm text-neutral-500">Enregistrez une parcelle pour voir la météo de votre champ.</p>}
      {q.isLoading && <Loading label="Chargement de la météo…" />}
      {q.isError && <p className="text-sm text-neutral-500">Météo momentanément indisponible.</p>}
      {w && tone && (
        <div className="space-y-3">
          <div className={`p-3 rounded border text-sm flex items-start gap-2 ${tone.box}`}>
            <tone.Icon className={`w-5 h-5 shrink-0 mt-0.5 ${tone.icon}`} aria-hidden />
            <div>
              <span className="font-bold block">{w.summary.indicator}</span>
              <span>{w.summary.message}</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className={`p-2.5 rounded border ${w.summary.sowing_favorable ? "border-emerald-200 bg-emerald-50/50" : "border-neutral-200 bg-neutral-50"}`}>
              <span className="text-xs text-neutral-500 block">Semis</span>
              <span className="font-semibold">{w.summary.sowing_favorable ? "Moment favorable" : "Pas idéal"}</span>
            </div>
            <div className={`p-2.5 rounded border ${w.summary.spraying_advised ? "border-emerald-200 bg-emerald-50/50" : "border-amber-200 bg-amber-50/50"}`}>
              <span className="text-xs text-neutral-500 block">Traitement aujourd'hui</span>
              <span className="font-semibold">{w.summary.spraying_advised ? "Possible" : "À éviter"}</span>
            </div>
          </div>
          <ol className="grid grid-cols-7 gap-1 text-center text-xs" aria-label="Prévisions sur 7 jours">
            {w.days.slice(0, 7).map((d) => (
              <li key={d.date} className="p-1.5 rounded bg-neutral-50 border border-neutral-100">
                <span className="block text-neutral-500 capitalize">{DAY.format(new Date(d.date))}</span>
                <span className="block font-bold tabular-nums">{Math.round(d.tmax)}°</span>
                <span className={`block tabular-nums ${d.precipitation_mm >= 30 ? "text-red-700 font-bold" : d.precipitation_mm >= 2 ? "text-blue-700" : "text-neutral-400"}`}>
                  {Math.round(d.precipitation_mm)} mm
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Card>
  );
}
