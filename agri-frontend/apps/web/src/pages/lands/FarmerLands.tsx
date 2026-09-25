import { api, apiErrorMessage, formatDate, formatFcfa, formatNumber } from "@agri/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Award, CalendarClock, FileText, Landmark, MapPin, Scale, Sprout } from "lucide-react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { MapView } from "../../components/MapView";
import { Alert, Badge, Button, Card, CardHeader, Empty, Loading } from "../../components/ui";
import { featureBounds } from "../../lib/geometry";
import { unwrap, useMyPerformance } from "../../lib/queries";
import { APP_STATUS, type Concession, CONTRACT, type Eligibility, PHASE, type Plan, type PublicCall } from "./types";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";
const Field = ({ id, label, children }: { id: string; label: string; children: ReactNode }) => (
  <div><label htmlFor={id} className="block text-sm font-semibold mb-1">{label}</label>{children}</div>
);

function ApplyForm({ call, onDone }: { call: PublicCall; onDone: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ proposed_crop: call.allowed_crops[0] ?? "", planned_yield_kg: "", motivation: "", experience_years: "" });
  const apply = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/calls/{call_id}/applications", { params: { path: { call_id: call.id } }, body: {
      proposed_crop: f.proposed_crop, planned_yield_kg: Number(f.planned_yield_kg), motivation: f.motivation,
      experience_years: f.experience_years ? Number(f.experience_years) : undefined,
    } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["calls"] }); onDone(); },
  });
  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); apply.mutate(); }} className="grid gap-3 sm:grid-cols-2 p-3 rounded-lg border border-emerald-200 bg-emerald-50/40">
      <Field id={`ac-${call.id}`} label="Culture proposée"><select id={`ac-${call.id}`} value={f.proposed_crop} onChange={(e) => setF({ ...f, proposed_crop: e.target.value })} className={inputCls}>{call.allowed_crops.map((c) => <option key={c}>{c}</option>)}</select></Field>
      <Field id={`ay-${call.id}`} label={`Production prévue sur ${formatNumber(call.surface_hectares, 1)} ha (kg par saison)`}><input id={`ay-${call.id}`} inputMode="numeric" value={f.planned_yield_kg} onChange={(e) => setF({ ...f, planned_yield_kg: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
      <Field id={`ax-${call.id}`} label="Années d'expérience"><input id={`ax-${call.id}`} inputMode="numeric" value={f.experience_years} onChange={(e) => setF({ ...f, experience_years: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
      <div className="sm:col-span-2"><Field id={`am-${call.id}`} label="Votre projet (au moins 20 caractères)"><textarea id={`am-${call.id}`} rows={4} maxLength={3000} value={f.motivation} onChange={(e) => setF({ ...f, motivation: e.target.value })} className={inputCls} placeholder="Ce que vous cultiverez, avec qui, avec quels moyens, comment vous respecterez le cahier des charges." /></Field></div>
      {apply.isError && <div className="sm:col-span-2"><Alert tone="error">{(apply.error as Error).message}</Alert></div>}
      <Button type="submit" className="sm:col-span-2" loading={apply.isPending} disabled={!f.planned_yield_kg || f.motivation.trim().length < 20}>Déposer ma candidature</Button>
      <p className="sm:col-span-2 text-xs text-neutral-500">Votre score est figé au moment du dépôt. Vous pourrez retirer votre candidature tant que l'appel est ouvert.</p>
    </form>
  );
}

function CallCard({ call }: { call: PublicCall }) {
  const [open, setOpen] = useState(false);
  const [applying, setApplying] = useState(false);
  const [done, setDone] = useState(false);
  const el = useQuery({
    queryKey: ["calls", call.id, "eligibility"],
    enabled: open,
    queryFn: async () => unwrap(await api.GET("/api/v1/calls/{call_id}/eligibility/me", { params: { path: { call_id: call.id } } })) as unknown as Eligibility,
  });
  const fc = useMemo<GeoJSON.FeatureCollection>(() => ({ type: "FeatureCollection", features: [{ type: "Feature", properties: { id: call.id, verification_status: "verifiee" }, geometry: call.boundary as unknown as GeoJSON.Geometry }] }), [call]);
  // Résumé public du plan (seuls les plans validés par un expert sont publiés) : champs renvoyés par /calls
  const plan = call.plan_summary as unknown as (Pick<Plan, "summary" | "risks"> & { indicators: Plan["valorization_indicators"]; recommended_scenario: string;
    crops: string[]; rotation: string; calendar: Plan["scenarios"][number]["calendar"]; reviewed_by?: string }) | null;
  return (
    <li className="border border-neutral-200 rounded-lg bg-white">
      <div className="p-4 space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="font-bold text-base">{call.domain_name}</h3>
            <p className="text-sm text-neutral-600 flex items-center gap-1"><MapPin className="w-3.5 h-3.5" aria-hidden /> {call.commune} ({call.department}) · {formatNumber(call.surface_hectares, 1)} ha</p>
          </div>
          <Badge tone={call.phase === "ouvert" ? "green" : "neutral"}>{call.phase ? PHASE[call.phase] : call.status}</Badge>
        </div>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
          <div><dt className="text-xs text-neutral-500">Cultures</dt><dd className="font-semibold">{call.allowed_crops.join(", ")}</dd></div>
          <div><dt className="text-xs text-neutral-500">{CONTRACT[call.contract_type]}</dt><dd className="font-semibold">{call.duration_years} ans</dd></div>
          <div><dt className="text-xs text-neutral-500">Redevance</dt><dd className="font-semibold tabular-nums">{formatNumber(call.annual_fee_fcfa_per_ha)} FCFA/ha/an</dd></div>
          <div><dt className="text-xs text-neutral-500">Clôture</dt><dd className="font-semibold">{formatDate(call.closes_at)}</dd></div>
        </dl>
        <p className="text-sm text-neutral-600">Score minimal : {formatNumber(call.min_score)} / 100 · {call.applications_count} candidature{call.applications_count > 1 ? "s" : ""}</p>
        <Button variant="outline" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Masquer le détail" : "Voir le détail et candidater"}</Button>
      </div>
      {open && (
        <div className="p-4 border-t border-neutral-100 space-y-4">
          <MapView className="h-64" parcels={fc} fitBounds={featureBounds(fc)} label="Terre de l'État" />
          <div><h4 className="text-sm font-bold mb-1">Description</h4><p className="text-sm">{call.description}</p></div>
          <details className="text-sm"><summary className="font-semibold cursor-pointer min-h-11 flex items-center">Cahier des charges</summary><pre className="whitespace-pre-wrap font-sans text-neutral-700">{call.cahier_des_charges}</pre></details>
          {plan && (
            <div className="p-3 rounded-lg border border-emerald-200 bg-emerald-50/40">
              <h4 className="text-sm font-bold mb-2 flex items-center gap-2"><Sprout className="w-4 h-4 text-emerald-800" aria-hidden /> Plan de mise en valeur de référence{plan.reviewed_by ? ` (relu par ${plan.reviewed_by})` : ""}</h4>
              <p className="text-sm mb-2">{plan.summary}</p>
              <p className="text-sm"><strong>Scénario recommandé : </strong>{plan.recommended_scenario} · {(plan.crops ?? []).join(", ")} · {plan.rotation}</p>
              <ol className="text-sm mt-2 space-y-0.5">{(plan.calendar ?? []).map((c, k) => <li key={k}><strong>{c.period} :</strong> {c.activity}</li>)}</ol>
              {!!plan.indicators?.length && <p className="text-sm mt-2"><strong>Indicateurs contrôlés : </strong>{plan.indicators.map((v) => `${v.indicator} (${v.target})`).join(" ; ")}</p>}
            </div>
          )}
          {el.isLoading && <Loading label="Vérification de votre éligibilité…" />}
          {el.data && (done || el.data.already_applied ? <Alert tone="success">Votre candidature est déposée. Suivez-la dans « Mes candidatures ».</Alert>
            : el.data.eligible ? (applying ? <ApplyForm call={call} onDone={() => setDone(true)} /> : (
              <div className="space-y-2">
                <Alert tone="success">Vous êtes éligible (score {formatNumber(el.data.score, 1)} / 100, minimum {formatNumber(el.data.min_score)}).</Alert>
                <Button onClick={() => setApplying(true)}>Candidater</Button>
              </div>
            )) : (
              <Alert tone="warning"><strong>Vous ne pouvez pas candidater pour l'instant :</strong><ul className="list-disc pl-5 mt-1">{el.data.reasons.map((r) => <li key={r}>{r}</li>)}</ul></Alert>
            ))}
        </div>
      )}
    </li>
  );
}

function MyApplications() {
  const qc = useQueryClient();
  const apps = useQuery({ queryKey: ["calls", "applications", "me"], queryFn: async () => unwrap(await api.GET("/api/v1/calls/applications/me")) });
  const calls = useQuery({ queryKey: ["calls", "public", "all"], queryFn: async () => unwrap(await api.GET("/api/v1/calls")) });
  const byId = Object.fromEntries((calls.data ?? []).map((c) => [c.id, c]));
  const [reason, setReason] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const act = async (fn: () => Promise<{ error?: unknown }>, ok: string) => {
    const { error } = await fn();
    setMsg(error ? { tone: "error", text: apiErrorMessage(error) } : { tone: "success", text: ok });
    qc.invalidateQueries({ queryKey: ["calls"] });
    qc.invalidateQueries({ queryKey: ["concessions"] });
  };
  if (apps.isLoading) return <Loading />;
  if (!apps.data?.length) return <Empty>Aucune candidature pour le moment.</Empty>;
  return (
    <div className="space-y-3">
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      <ul className="space-y-3">
        {apps.data.map((a) => {
          const call = byId[a.call_id];
          const [label, tone] = APP_STATUS[a.status];
          const contestable = call && call.status === "attribue" && a.status === "deposee" && call.contest_until && new Date(call.contest_until) > new Date();
          return (
            <li key={a.id} className="p-4 border border-neutral-200 rounded-lg space-y-2">
              <div className="flex flex-wrap justify-between gap-2">
                <span className="font-semibold">{call?.domain_name ?? "Appel"} · {a.proposed_crop}</span>
                <Badge tone={tone}>{label}</Badge>
              </div>
              <p className="text-sm text-neutral-600">Déposée le {formatDate(a.created_at)} · score au dépôt : {formatNumber(a.score_at_submission, 1)} / 100</p>
              {a.status === "deposee" && call?.phase === "ouvert" && (
                <Button variant="ghost" onClick={() => act(() => api.DELETE("/api/v1/calls/{call_id}/applications/me", { params: { path: { call_id: a.call_id } } }), "Candidature retirée.")}>Retirer ma candidature</Button>
              )}
              {a.status === "retenue" && call?.status === "attribue" && (
                <div className="p-3 rounded border border-emerald-300 bg-emerald-50 space-y-2">
                  <p className="text-sm font-semibold">Félicitations, vous êtes retenu(e) ! Confirmez-vous l'attribution ?</p>
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={() => act(() => api.POST("/api/v1/calls/{call_id}/acceptance", { params: { path: { call_id: a.call_id } }, body: { accept: true } }), "Acceptation enregistrée. La concession sera active après signature de l'acte officiel.")}>J'accepte</Button>
                    <Button variant="danger" onClick={() => window.confirm("Renoncer à cette terre ?") && act(() => api.POST("/api/v1/calls/{call_id}/acceptance", { params: { path: { call_id: a.call_id } }, body: { accept: false } }), "Désistement enregistré.")}>Je renonce</Button>
                  </div>
                </div>
              )}
              {contestable && (
                <details className="text-sm">
                  <summary className="cursor-pointer font-semibold text-emerald-800 min-h-11 flex items-center gap-1.5"><Scale className="w-4 h-4" aria-hidden /> Contester l'attribution (jusqu'au {formatDate(call.contest_until!)})</summary>
                  <textarea aria-label="Motif de la contestation" rows={3} value={reason[a.id] ?? ""} onChange={(e) => setReason({ ...reason, [a.id]: e.target.value })} className={inputCls} placeholder="Expliquez précisément ce qui vous paraît irrégulier (au moins 20 caractères)." />
                  <Button className="mt-2" variant="outline" disabled={(reason[a.id] ?? "").trim().length < 20}
                          onClick={() => act(() => api.POST("/api/v1/calls/{call_id}/contestations", { params: { path: { call_id: a.call_id } }, body: { reason: reason[a.id] } }), "Contestation déposée : un superviseur va l'examiner.")}>Déposer la contestation</Button>
                </details>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function MyConcessions() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["concessions", "me"], queryFn: async () => unwrap(await api.GET("/api/v1/concessions/me")) as unknown as Concession[] });
  const [report, setReport] = useState({ season: `${new Date().getFullYear()}-A`, crop_type: "", area_cultivated_ha: "", actual_yield_kg: "" });
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  if (q.isLoading) return <Loading />;
  if (!q.data?.length) return <Empty>Aucune concession pour le moment.</Empty>;
  const send = async (c: Concession) => {
    const { error } = await api.POST("/api/v1/concessions/{concession_id}/reports", { params: { path: { concession_id: c.id } }, body: {
      season: report.season, crop_type: report.crop_type || c.crop_type, area_cultivated_ha: Number(report.area_cultivated_ha.replace(",", ".")), actual_yield_kg: Number(report.actual_yield_kg),
    } });
    setMsg(error ? { tone: "error", text: apiErrorMessage(error) } : { tone: "success", text: "Récolte déclarée." });
    qc.invalidateQueries({ queryKey: ["concessions"] });
  };
  const STATUS = { en_attente_acte: ["En attente de l'acte officiel", "amber"], active: ["Active", "green"], retiree: ["Retirée", "red"], terminee: ["Terminée", "neutral"], annulee: ["Annulée", "neutral"] } as const;
  return (
    <ul className="space-y-4">
      {q.data.map((c) => {
        const [label, tone] = STATUS[c.status];
        return (
          <li key={c.id} className="p-4 border border-neutral-200 rounded-lg space-y-3">
            <div className="flex flex-wrap justify-between gap-2">
              <div><h3 className="font-bold">{c.domain_name}</h3><p className="text-sm text-neutral-600">{c.commune} · {formatNumber(c.surface_hectares, 1)} ha · {c.crop_type}</p></div>
              <Badge tone={tone}>{label}</Badge>
            </div>
            {c.status === "active" && (
              <>
                <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
                  <div><dt className="text-xs text-neutral-500">Acte</dt><dd className="font-semibold">{c.act_ref}</dd></div>
                  <div><dt className="text-xs text-neutral-500">Fin</dt><dd className="font-semibold">{c.end_date ? formatDate(c.end_date) : "—"}</dd></div>
                  <div><dt className="text-xs text-neutral-500">Mise en valeur constatée</dt><dd className="font-semibold">{c.latest_mise_en_valeur_pct != null ? `${formatNumber(c.latest_mise_en_valeur_pct)} %` : "pas encore inspectée"}</dd></div>
                  <div><dt className="text-xs text-neutral-500">Redevance restant due</dt><dd className={`font-semibold tabular-nums ${c.balance_fcfa > 0 ? "text-red-700" : ""}`}>{formatFcfa(c.balance_fcfa)}</dd></div>
                </dl>
                {c.mise_en_valeur_alert && <Alert tone="error">Le délai de mise en valeur est dépassé avec moins de 50 % constatés : risque de retrait. Contactez votre agent.</Alert>}
                {c.mise_en_valeur_deadline && !c.mise_en_valeur_alert && <p className="text-sm flex items-center gap-1.5"><CalendarClock className="w-4 h-4 text-emerald-800" aria-hidden /> Mise en valeur attendue avant le {formatDate(c.mise_en_valeur_deadline)}</p>}
                <form onSubmit={(e) => { e.preventDefault(); send(c); }} className="grid gap-2 sm:grid-cols-4 items-end p-3 rounded bg-neutral-50 border border-neutral-200">
                  <Field id={`rs-${c.id}`} label="Saison"><input id={`rs-${c.id}`} value={report.season} onChange={(e) => setReport({ ...report, season: e.target.value.toUpperCase() })} className={inputCls} /></Field>
                  <Field id={`ra-${c.id}`} label="Surface cultivée (ha)"><input id={`ra-${c.id}`} inputMode="decimal" value={report.area_cultivated_ha} onChange={(e) => setReport({ ...report, area_cultivated_ha: e.target.value })} className={inputCls} /></Field>
                  <Field id={`ry-${c.id}`} label="Récolte (kg)"><input id={`ry-${c.id}`} inputMode="numeric" value={report.actual_yield_kg} onChange={(e) => setReport({ ...report, actual_yield_kg: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
                  <Button type="submit" disabled={!report.area_cultivated_ha || !report.actual_yield_kg}>Déclarer la récolte</Button>
                </form>
              </>
            )}
            {c.status === "en_attente_acte" && <p className="text-sm text-neutral-600">Vous avez accepté l'attribution. La concession démarrera à l'enregistrement de l'acte signé par l'autorité compétente.</p>}
          </li>
        );
      })}
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
    </ul>
  );
}

export function FarmerLands() {
  const perf = useMyPerformance();
  const calls = useQuery({ queryKey: ["calls", "public", "ouvert"], queryFn: async () => unwrap(await api.GET("/api/v1/calls", { params: { query: { phase: "ouvert" } } })) });
  const [tab, setTab] = useState<"appels" | "candidatures" | "concessions">("appels");
  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight flex items-center gap-2"><Landmark className="w-5 h-5 text-emerald-800" aria-hidden /> Terres de l'État</h1>
            <p className="text-sm text-neutral-600 mt-1">Des terres du domaine privé de l'État sont attribuées par appel à candidatures, en concession, à charge de les mettre en valeur.</p>
          </div>
          {perf.data && <Badge tone={perf.data.eligible ? "green" : "amber"}><Award className="w-3.5 h-3.5" aria-hidden /> Mon score : {formatNumber(perf.data.score, 0)} / 100</Badge>}
        </div>
        <div role="tablist" className="flex gap-1 bg-neutral-100 p-1 rounded border border-neutral-200 overflow-x-auto mt-4">
          {([["appels", "Appels ouverts"], ["candidatures", "Mes candidatures"], ["concessions", "Mes concessions"]] as const).map(([t, l]) => (
            <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                    className={`min-h-10 px-3 rounded text-sm font-semibold whitespace-nowrap shrink-0 cursor-pointer ${tab === t ? "bg-white shadow-sm text-emerald-900" : "text-neutral-600"}`}>{l}</button>
          ))}
        </div>
      </Card>
      {tab === "appels" && (
        <Card>
          <CardHeader icon={FileText} title="Appels à candidatures ouverts" />
          {calls.isLoading && <Loading />}
          {calls.isSuccess && !calls.data.length && <Empty>Aucun appel ouvert en ce moment. Vous serez prévenu par une notification.</Empty>}
          <ul className="space-y-4">{calls.data?.map((c) => <CallCard key={c.id} call={c} />)}</ul>
        </Card>
      )}
      {tab === "candidatures" && <Card><CardHeader title="Mes candidatures" /><MyApplications /></Card>}
      {tab === "concessions" && <Card><CardHeader title="Mes concessions" /><MyConcessions /></Card>}
    </div>
  );
}
