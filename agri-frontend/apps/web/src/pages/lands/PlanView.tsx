import { formatNumber } from "@agri/core";
import { AlertTriangle, CalendarDays, Leaf, ListChecks, Target } from "lucide-react";
import { useState } from "react";
import { Badge } from "../../components/ui";
import type { Plan } from "./types";

const SUIT = { elevee: ["Élevée", "green"], moyenne: ["Moyenne", "amber"], faible: ["Faible", "red"], deconseillee: ["Déconseillée", "red"] } as const;
const LIKE = { faible: "neutral", moyen: "amber", eleve: "red" } as const;
const range = (r: { low: number; high: number }) => `${formatNumber(r.low)} à ${formatNumber(r.high)}`;

/** Affichage d'un plan de mise en valeur : aptitude, scénarios, calendrier, fertilité, risques, indicateurs. */
export function PlanView({ plan, compact = false }: { plan: Plan; compact?: boolean }) {
  const [i, setI] = useState(plan.recommended_scenario_index);
  const sc = plan.scenarios[i];
  return (
    <div className="space-y-5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={plan.confidence === "elevee" ? "green" : plan.confidence === "moyenne" ? "amber" : "red"}>Confiance : {plan.confidence}</Badge>
      </div>
      <p className="text-base">{plan.summary}</p>

      {!compact && (
        <div>
          <h3 className="font-bold mb-2 flex items-center gap-2"><Leaf className="w-4 h-4 text-emerald-800" aria-hidden /> Aptitude des cultures</h3>
          <ul className="grid gap-2 sm:grid-cols-2">
            {plan.suitability.map((s) => {
              const [label, tone] = SUIT[s.suitability];
              return (
                <li key={s.crop} className="p-2.5 rounded border border-neutral-200">
                  <div className="flex justify-between gap-2"><span className="font-semibold">{s.crop}</span><Badge tone={tone}>{label} · {formatNumber(s.score, 1)}/10</Badge></div>
                  <p className="text-neutral-600 mt-1">{s.reasons.join(" · ")}</p>
                  {!!s.limiting_factors?.length && <p className="text-amber-800 mt-0.5">Limites : {s.limiting_factors.join(", ")}</p>}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div>
        <h3 className="font-bold mb-2">Scénarios</h3>
        <div role="tablist" className="flex gap-1 overflow-x-auto mb-3">
          {plan.scenarios.map((s, k) => (
            <button key={k} type="button" role="tab" aria-selected={k === i} onClick={() => setI(k)}
                    className={`min-h-10 px-3 rounded border text-sm font-semibold whitespace-nowrap cursor-pointer ${k === i ? "border-emerald-800 bg-emerald-50 text-emerald-950" : "border-neutral-300 text-neutral-700"}`}>
              {s.name}{k === plan.recommended_scenario_index ? " (recommandé)" : ""}
            </button>
          ))}
        </div>
        {i === plan.recommended_scenario_index && <p className="text-neutral-700 mb-2"><strong>Pourquoi : </strong>{plan.recommendation_rationale}</p>}
        <div className="p-3 rounded-lg border border-neutral-200 bg-neutral-50 space-y-2">
          <p><strong>Cultures : </strong>{sc.crops.join(", ")} · <strong>Rotation : </strong>{sc.rotation}</p>
          <p><strong>Répartition : </strong>{sc.surface_allocation.map((a) => `${a.crop} ${formatNumber(a.share_pct)} %`).join(", ")}</p>
          <div className="overflow-x-auto">
            <table className="w-full [&_td]:whitespace-nowrap">
              <thead><tr className="text-left text-neutral-500"><th className="py-1 pr-3 font-semibold">Culture</th><th className="py-1 font-semibold text-right">Rendement (kg/ha)</th></tr></thead>
              <tbody className="tabular-nums">{sc.yields.map((y) => <tr key={y.crop} className="border-t border-neutral-200"><td className="py-1 pr-3">{y.crop}</td><td className="py-1 text-right">{range(y.yield_kg_ha)}</td></tr>)}</tbody>
            </table>
          </div>
          <p className="tabular-nums"><strong>Coûts : </strong>{range(sc.costs_fcfa_ha)} FCFA/ha · <strong>Revenus : </strong>{range(sc.revenue_fcfa_ha)} FCFA/ha</p>
          <p><strong>Investissements : </strong>{sc.investments.join(", ") || "—"} · <strong>Main-d'œuvre : </strong>{sc.labor_needs}</p>
          <p className="text-emerald-900"><strong>+ </strong>{sc.advantages.join(" · ")}</p>
          <p className="text-red-800"><strong>− </strong>{sc.drawbacks.join(" · ")}</p>
        </div>
        <h4 className="font-bold mt-3 mb-1 flex items-center gap-2"><CalendarDays className="w-4 h-4 text-emerald-800" aria-hidden /> Calendrier cultural</h4>
        <ol className="space-y-1">{sc.calendar.map((c, k) => <li key={k}><span className="font-semibold">{c.period} :</span> {c.activity}{c.details ? ` (${c.details})` : ""}</li>)}</ol>
      </div>

      {!compact && (
        <div>
          <h3 className="font-bold mb-1">Plan de fertilité</h3>
          <ul className="list-disc pl-5 space-y-0.5">{plan.fertility_plan.map((f, k) => <li key={k}><strong>{f.action}</strong> ({f.timing}) : {f.rationale}</li>)}</ul>
        </div>
      )}
      <div>
        <h3 className="font-bold mb-1 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-amber-700" aria-hidden /> Risques et parades</h3>
        <ul className="space-y-1">{plan.risks.map((r, k) => <li key={k} className="flex flex-wrap gap-2 items-baseline"><Badge tone={LIKE[r.likelihood]}>{r.likelihood}</Badge><span><strong>{r.risk}</strong> : {r.mitigation}</span></li>)}</ul>
      </div>
      <div>
        <h3 className="font-bold mb-1 flex items-center gap-2"><Target className="w-4 h-4 text-emerald-800" aria-hidden /> Indicateurs de mise en valeur</h3>
        <ul className="space-y-1">{plan.valorization_indicators.map((v, k) => <li key={k}><strong>{v.indicator}</strong> : {v.target} sous {v.deadline_months} mois <span className="text-neutral-500">(contrôle : {v.how_to_check})</span></li>)}</ul>
      </div>
      {!compact && !!plan.data_gaps.length && (
        <div className="p-3 rounded border border-amber-200 bg-amber-50">
          <h3 className="font-bold mb-1 flex items-center gap-2"><ListChecks className="w-4 h-4" aria-hidden /> Données manquantes ou incertaines</h3>
          <ul className="list-disc pl-5">{plan.data_gaps.map((g) => <li key={g}>{g}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
