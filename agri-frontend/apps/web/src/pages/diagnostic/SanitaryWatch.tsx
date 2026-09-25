import { api, formatDate, formatNumber } from "@agri/core";
import { useQuery } from "@tanstack/react-query";
import { Bug, Map as MapIcon } from "lucide-react";
import { useState } from "react";
import { MapView } from "../../components/MapView";
import { Badge, Card, CardHeader, Empty, Loading } from "../../components/ui";
import { unwrap } from "../../lib/queries";

interface Zone { department: string; commune: string; disease: string | null; crop: string | null; cases: number; critical_cases: number;
  affected_farmers: number; last_seen: string; is_hotspot: boolean; alert_level: "red" | "orange" | "yellow" }

/** Veille sanitaire des agents : foyers par commune et carte des diagnostics localisés. */
export function SanitaryWatch() {
  const [days, setDays] = useState(30);
  const hot = useQuery({
    queryKey: ["state", "hotspots", days],
    queryFn: async () => unwrap(await api.GET("/api/v1/state/sanitary/hotspots", { params: { query: { days } } })) as unknown as { zones: Zone[]; hotspot_threshold: number },
  });
  const points = useQuery({
    queryKey: ["state", "map", "alerts", days],
    queryFn: async () => unwrap(await api.GET("/api/v1/state/map/alerts", { params: { query: { days } } })) as unknown as GeoJSON.FeatureCollection,
  });
  const zones = hot.data?.zones ?? [];
  const hotspots = zones.filter((z) => z.is_hotspot);
  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Veille sanitaire</h1>
            <p className="text-sm text-neutral-600">Diagnostics des exploitants, regroupés par commune et par maladie.</p>
          </div>
          <label className="text-sm flex items-center gap-2">Période
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="min-h-10 px-2 border border-neutral-300 rounded bg-white">
              <option value={7}>7 jours</option><option value={30}>30 jours</option><option value={90}>90 jours</option>
            </select>
          </label>
        </div>
      </Card>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <Card className="lg:col-span-7">
          <CardHeader icon={MapIcon} title={`Diagnostics localisés (${points.data?.features.length ?? 0})`} />
          <MapView className="h-[60vh] min-h-80" points={points.data} label="Carte des diagnostics" />
        </Card>
        <Card className="lg:col-span-5">
          <CardHeader icon={Bug} title={`Foyers (${hotspots.length})`} action={hot.data && <span className="text-xs text-neutral-500">Seuil : {hot.data.hotspot_threshold} cas</span>} />
          {hot.isLoading && <Loading />}
          {hot.isSuccess && !zones.length && <Empty>Aucun cas signalé sur la période.</Empty>}
          <ul className="space-y-2">
            {zones.slice(0, 20).map((z, i) => (
              <li key={i} className={`p-3 rounded border text-sm ${z.alert_level === "red" ? "border-red-300 bg-red-50" : z.alert_level === "orange" ? "border-orange-300 bg-orange-50" : "border-neutral-200"}`}>
                <div className="flex items-start justify-between gap-2">
                  <span className="font-semibold">{z.disease ?? "Problème non identifié"}</span>
                  {z.is_hotspot && <Badge tone={z.alert_level === "red" ? "red" : "amber"}>Foyer</Badge>}
                </div>
                <p className="text-neutral-700">{z.commune} ({z.department}) · {z.crop}</p>
                <p className="text-neutral-600 tabular-nums">
                  {formatNumber(z.cases)} cas dont {formatNumber(z.critical_cases)} critiques · {z.affected_farmers} exploitant{z.affected_farmers > 1 ? "s" : ""} · dernier le {formatDate(z.last_seen)}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
