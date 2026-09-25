import { api, formatFcfa, formatFcfaCompact, formatHectares, formatNumber, useSession } from "@agri/core";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Coins, Gauge, HeartPulse, ListChecks } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardHeader, Loading } from "../components/ui";
import { unwrap } from "../lib/queries";

type Metrics = Record<string, number>;
interface Priority { kind: string; commune: string; department: string; priority: number; reason: string }

const KIND = { verification: "Vérification", rendement_anormal: "Rendement anormal", concession: "Concession", foyer_sanitaire: "Foyer sanitaire" } as Record<string, string>;

/** Accueil agent et superviseur (version complète à l'étape 4). */
export function AgentHome() {
  const { user } = useSession();
  const supervisor = user?.role === "state_supervisor";
  const metrics = useQuery({ queryKey: ["state", "metrics"], queryFn: async () => unwrap(await api.GET("/api/v1/state/dashboard-metrics")) as Metrics });
  const priorities = useQuery({
    queryKey: ["state", "priorities"],
    queryFn: async () => unwrap(await api.GET("/api/v1/state/inspection-priorities", { params: { query: { limit: 8 } } })) as unknown as Priority[],
  });
  const m = metrics.data;
  const kpis = m
    ? [
        ["Parcelles suivies", formatNumber(m.parcels_monitored)],
        ["Surface déclarée", formatHectares(m.surface_total_ha)],
        ["Menaces sanitaires (30 j)", formatNumber(m.phytosanitary_threats_last_30_days ?? 0)],
        ["Litiges ouverts", formatNumber(m.open_disputes)],
        ["Ventes déclarées", formatFcfaCompact(m.market_sold_volume_fcfa), formatFcfa(m.market_sold_volume_fcfa)],
        ["Concessions actives", formatNumber(m.concessions_active ?? 0)],
      ]
    : [];
  return (
    <div className="space-y-5 sm:space-y-6">
      <Card>
        <p className="text-xs font-bold text-emerald-800">{supervisor ? "Cockpit État" : "Guichet agent"}</p>
        <h1 className="text-xl font-bold tracking-tight text-neutral-900">{user?.full_name}</h1>
        {metrics.isLoading && <Loading />}
        {m && (
          <dl className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-px bg-neutral-200 border border-neutral-200 rounded-lg overflow-hidden mt-4">
            {kpis.map(([label, value, title]) => (
              <div key={label} className="bg-white p-3.5 flex flex-col-reverse gap-0.5">
                <dt className="text-xs text-neutral-500">{label}</dt>
                <dd className="text-lg font-bold tabular-nums whitespace-nowrap" title={title}>{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </Card>
      <Card>
        <CardHeader icon={ListChecks} title="Où aller en priorité" />
        {priorities.isLoading && <Loading />}
        <ul className="divide-y divide-neutral-100">
          {(priorities.data ?? []).map((p, i) => (
            <li key={i} className="py-2.5 flex items-start gap-3 text-sm">
              <span className={`mt-0.5 min-w-10 text-center px-1.5 py-0.5 rounded text-xs font-bold tabular-nums ${p.priority >= 80 ? "bg-red-100 text-red-800" : p.priority >= 60 ? "bg-amber-100 text-amber-900" : "bg-neutral-100 text-neutral-700"}`}>
                {p.priority}
              </span>
              <span className="flex-1">
                <span className="font-semibold">{KIND[p.kind] ?? p.kind}</span> · {p.commune} ({p.department})
                <span className="block text-neutral-600">{p.reason}</span>
              </span>
            </li>
          ))}
        </ul>
      </Card>
      <div className="flex flex-wrap gap-4 items-center">
        <Link to="/finances" className="inline-flex items-center gap-2 text-sm font-semibold text-blue-800 bg-blue-50 hover:bg-blue-100 border border-blue-200 px-3 py-2 rounded-lg">
          <Coins className="w-4 h-4 text-blue-700" aria-hidden /> Guichet Financement & Crédit <ArrowRight className="w-4 h-4" aria-hidden />
        </Link>
        <Link to="/sante" className="inline-flex items-center gap-2 text-sm font-semibold text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 px-3 py-2 rounded-lg">
          <HeartPulse className="w-4 h-4 text-red-600" aria-hidden /> Urgences Santé Exploitants <ArrowRight className="w-4 h-4" aria-hidden />
        </Link>
        <Link to="/supervision" className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-800 hover:underline">
          <Gauge className="w-4 h-4" aria-hidden /> Supervision détaillée <ArrowRight className="w-4 h-4" aria-hidden />
        </Link>
      </div>
    </div>
  );
}
