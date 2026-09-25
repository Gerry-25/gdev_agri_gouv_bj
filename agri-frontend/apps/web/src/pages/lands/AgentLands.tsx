import { api, apiErrorMessage, formatDate, formatFcfa, formatNumber, useSession } from "@agri/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Gavel, Landmark, Plus, ShieldCheck, Sparkles, Users } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { MapView } from "../../components/MapView";
import { Alert, Badge, Button, buttonClass, Card, CardHeader, Empty, Loading } from "../../components/ui";
import { DEPARTMENTS } from "../../lib/benin";
import { featureBounds } from "../../lib/geometry";
import { type Performance, unwrap } from "../../lib/queries";
import { type AdminCall, type Application, APP_STATUS, CALL_STATUS, type Concession, type ConcessionReview, PHASE } from "./types";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";
const Field = ({ id, label, children, className = "" }: { id: string; label: string; children: ReactNode; className?: string }) => (
  <div className={className}><label htmlFor={id} className="block text-sm font-semibold mb-1">{label}</label>{children}</div>
);
function useAction() {
  const qc = useQueryClient();
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const run = async (fn: () => Promise<{ error?: unknown }>, ok: string) => {
    const { error } = await fn();
    setMsg(error ? { tone: "error", text: apiErrorMessage(error) } : { tone: "success", text: ok });
    ["calls", "concessions", "domains", "applications"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    return !error;
  };
  return { msg, run, Msg: () => (msg ? <Alert tone={msg.tone}>{msg.text}</Alert> : null) };
}

// --- Terres --------------------------------------------------------------------------------

function Domains() {
  const navigate = useNavigate();
  const list = useQuery({ queryKey: ["domains"], queryFn: async () => unwrap(await api.GET("/api/v1/domains")) });
  const geo = useQuery({ queryKey: ["domains", "geojson"], queryFn: async () => unwrap(await api.GET("/api/v1/domains/geojson")) as unknown as GeoJSON.FeatureCollection });
  const fc = useMemo(() => geo.data && ({ ...geo.data, features: geo.data.features.map((f) => ({ ...f, properties: { ...f.properties, verification_status: "verifiee" } })) }), [geo.data]);
  const STATUS = { disponible: ["Disponible", "green"], appel_en_cours: ["Appel en cours", "blue"], attribue: ["Attribuée", "purple"], retire: ["Retirée", "neutral"] } as const;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
      <Card className="lg:col-span-7">
        <CardHeader icon={Landmark} title={`Terres de l'État (${list.data?.length ?? 0})`} action={<Link to="/concessions/terres/nouvelle" className={buttonClass("primary", "min-h-9")}><Plus className="w-4 h-4" aria-hidden /> Enregistrer</Link>} />
        <MapView className="h-[52vh] min-h-72" parcels={fc} fitBounds={featureBounds(fc)} onParcelClick={(id) => navigate(`/concessions/terres/${id}`)} label="Carte des terres de l'État" />
      </Card>
      <Card className="lg:col-span-5">
        <CardHeader title="Liste" />
        {list.isLoading && <Loading />}
        <ul className="divide-y divide-neutral-100">
          {list.data?.map((d) => {
            const [l, tone] = STATUS[d.status];
            return (
              <li key={d.id}>
                <Link to={`/concessions/terres/${d.id}`} className="py-3 flex items-center justify-between gap-2 hover:text-emerald-800">
                  <span><span className="font-semibold block">{d.name}</span><span className="text-sm text-neutral-600">{d.commune} · {formatNumber(d.surface_hectares, 1)} ha{d.dispute_flag ? " · en litige" : ""}</span></span>
                  <Badge tone={tone}>{l}</Badge>
                </Link>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}

// --- Appels ---------------------------------------------------------------------------------

interface AppReview { alignment: string; strengths: string[]; gaps: string[]; risks: string[]; questions_for_interview: string[]; yield_assessment: string; comment: string; yield_check: string }

function ApplicationRow({ app, call, canPropose }: { app: Application & { ai_review?: AppReview }; call: AdminCall; canPropose: boolean }) {
  const [review, setReview] = useState<AppReview | undefined>(app.ai_review);
  const [justif, setJustif] = useState("");
  const { run, Msg } = useAction();
  const ai = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/calls/{call_id}/applications/{application_id}/ai-review", { params: { path: { call_id: call.id, application_id: app.id } } })) as unknown as AppReview,
    onSuccess: setReview,
  });
  const [label, tone] = APP_STATUS[app.status];
  return (
    <li className="p-3 border border-neutral-200 rounded-lg space-y-2 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span><span className="font-bold tabular-nums">#{app.rank}</span> · <span className="font-semibold">{app.farmer_name}</span> · score {formatNumber(app.score_at_submission, 1)}{app.current_score != null ? ` (actuel ${formatNumber(app.current_score, 1)})` : ""}</span>
        <Badge tone={tone}>{label}</Badge>
      </div>
      <p>{app.proposed_crop} · {formatNumber(app.planned_yield_kg)} kg prévus{app.experience_years != null ? ` · ${app.experience_years} ans d'expérience` : ""}</p>
      <p className="text-neutral-700">{app.motivation}</p>
      {!review ? <Button variant="soft" onClick={() => ai.mutate()} loading={ai.isPending}><Sparkles className="w-4 h-4" aria-hidden /> Aide à l'analyse (IA)</Button> : (
        <div className="p-2.5 rounded border border-emerald-200 bg-emerald-50/40 space-y-1">
          <p><strong>Alignement avec le plan :</strong> {review.alignment} · <strong>Rendement :</strong> {review.yield_check}</p>
          {!!review.strengths.length && <p><strong>Points forts :</strong> {review.strengths.join(" ; ")}</p>}
          {!!review.gaps.length && <p><strong>Écarts :</strong> {review.gaps.join(" ; ")}</p>}
          {!!review.risks.length && <p><strong>Risques :</strong> {review.risks.join(" ; ")}</p>}
          {!!review.questions_for_interview.length && <p><strong>Questions à poser :</strong> {review.questions_for_interview.join(" ; ")}</p>}
          <p className="text-xs text-neutral-500">Aide à l'analyse : ne remplace ni le classement officiel ni l'évaluation de l'agent.</p>
        </div>
      )}
      {ai.isError && <Alert tone="error">{(ai.error as Error).message}</Alert>}
      {canPropose && app.status === "deposee" && (
        <details>
          <summary className="cursor-pointer font-semibold text-emerald-800 min-h-11 flex items-center">Proposer ce candidat comme lauréat</summary>
          <textarea aria-label="Justification" rows={2} value={justif} onChange={(e) => setJustif(e.target.value)} className={inputCls} placeholder="Justification (au moins 20 caractères), obligatoire et tracée" />
          {app.rank !== 1 && <p className="text-xs text-amber-800 mt-1">Ce candidat n'est pas premier au classement : l'écart sera signalé au superviseur.</p>}
          <Button className="mt-2" disabled={justif.trim().length < 20} onClick={() => run(() => api.POST("/api/v1/calls/{call_id}/award-proposal", { params: { path: { call_id: call.id } }, body: { application_id: app.id, justification: justif } }), "Proposition envoyée au superviseur.")}>Envoyer la proposition</Button>
        </details>
      )}
      <Msg />
    </li>
  );
}

function CallAdminCard({ call }: { call: AdminCall }) {
  const { user } = useSession();
  const supervisor = user?.role === "state_supervisor";
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const { run, Msg } = useAction();
  const apps = useQuery({ queryKey: ["applications", call.id], enabled: open, queryFn: async () => unwrap(await api.GET("/api/v1/calls/{call_id}/applications", { params: { path: { call_id: call.id } } })) });
  const contests = useQuery({ queryKey: ["calls", call.id, "contestations"], enabled: open && call.status === "attribue", queryFn: async () => unwrap(await api.GET("/api/v1/calls/{call_id}/contestations", { params: { path: { call_id: call.id } } })) });
  const [label, tone] = CALL_STATUS[call.status];
  const award = call.award;
  const lapsed = call.status === "attribue" && award?.acceptance_deadline && !award.accepted_at && new Date(award.acceptance_deadline) < new Date();
  const canPropose = call.phase === "cloture" || !!lapsed;
  return (
    <li className="border border-neutral-200 rounded-lg bg-white">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="w-full p-4 text-left flex flex-wrap items-start justify-between gap-2 cursor-pointer">
        <span>
          <span className="font-bold block">{call.title}</span>
          <span className="text-sm text-neutral-600">{call.domain_name} · {call.commune} · {formatNumber(call.surface_hectares, 1)} ha · {call.applications_count} candidature(s) · clôture {formatDate(call.closes_at)}</span>
        </span>
        <span className="flex gap-1.5">{call.phase && <Badge>{PHASE[call.phase]}</Badge>}<Badge tone={tone}>{label}</Badge></span>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-neutral-100 pt-3">
          {call.status === "brouillon" && (
            supervisor && call.created_by !== user?.npi ? (
              <Button onClick={() => run(() => api.POST("/api/v1/calls/{call_id}/publish", { params: { path: { call_id: call.id } } }), "Appel publié : les exploitants éligibles sont prévenus.")}><ShieldCheck className="w-4 h-4" aria-hidden /> Publier l'appel</Button>
            ) : <Alert tone="info">En attente de publication par un superviseur (autre que le rédacteur).</Alert>
          )}
          {award && (
            <div className="p-3 rounded-lg border border-purple-200 bg-purple-50/50 text-sm space-y-1">
              <p><strong>Lauréat proposé :</strong> {award.farmer_name} (score {formatNumber(award.score, 1)})</p>
              <p><strong>Justification :</strong> {award.justification}</p>
              {award.deviation_from_ranking && <Alert tone="warning">Un candidat mieux classé a été écarté : vérifiez la justification.</Alert>}
              {award.approved_at && <p>Validé le {formatDate(award.approved_at)} · contestation jusqu'au {award.contest_until ? formatDate(award.contest_until) : "—"} · {award.accepted_at ? "accepté par le lauréat" : `réponse attendue avant le ${award.acceptance_deadline ? formatDate(award.acceptance_deadline) : "—"}`}</p>}
            </div>
          )}
          {call.status === "attribution_proposee" && (
            supervisor && award?.proposed_by !== user?.npi ? (
              <div className="space-y-2">
                <Field id={`an-${call.id}`} label="Motif de la décision"><input id={`an-${call.id}`} value={note} onChange={(e) => setNote(e.target.value)} className={inputCls} /></Field>
                <div className="flex flex-wrap gap-2">
                  <Button disabled={note.length < 5} onClick={() => run(() => api.POST("/api/v1/calls/{call_id}/award-decision", { params: { path: { call_id: call.id } }, body: { approve: true, note } }), "Attribution validée : le délai de contestation commence.")}><Gavel className="w-4 h-4" aria-hidden /> Valider l'attribution</Button>
                  <Button variant="danger" disabled={note.length < 5} onClick={() => run(() => api.POST("/api/v1/calls/{call_id}/award-decision", { params: { path: { call_id: call.id } }, body: { approve: false, note } }), "Proposition refusée.")}>Refuser</Button>
                </div>
              </div>
            ) : <Alert tone="info">En attente de validation par un superviseur (autre que l'auteur de la proposition).</Alert>
          )}
          {!!contests.data?.length && (
            <div className="space-y-2">
              <h4 className="text-sm font-bold">Contestations</h4>
              {contests.data.map((c) => (
                <div key={c.id} className="p-3 rounded border border-neutral-200 text-sm space-y-2">
                  <p>{c.reason}</p>
                  {c.status === "ouverte" && supervisor ? (
                    <div className="flex flex-wrap gap-2">
                      <Button variant="danger" onClick={() => run(() => api.PATCH("/api/v1/contestations/{contestation_id}", { params: { path: { contestation_id: c.id } }, body: { decision: "fondee", note: note || "Contestation jugée fondée" } }), "Contestation fondée : l'attribution est annulée.")}>Fondée</Button>
                      <Button variant="outline" onClick={() => run(() => api.PATCH("/api/v1/contestations/{contestation_id}", { params: { path: { contestation_id: c.id } }, body: { decision: "rejetee", note: note || "Contestation non fondée" } }), "Contestation rejetée.")}>Non fondée</Button>
                    </div>
                  ) : <Badge>{c.status}</Badge>}
                </div>
              ))}
            </div>
          )}
          {apps.isLoading && <Loading />}
          {!!apps.data?.length && (
            <div><h4 className="text-sm font-bold mb-2">Candidatures classées par score au dépôt</h4>
              <ul className="space-y-2">{apps.data.map((a) => <ApplicationRow key={a.id} app={a as never} call={call} canPropose={canPropose && ["publie", "attribue"].includes(call.status)} />)}</ul></div>
          )}
          {supervisor && ["brouillon", "publie", "attribution_proposee"].includes(call.status) && (
            <details className="text-sm">
              <summary className="cursor-pointer font-semibold text-red-700 min-h-11 flex items-center">Clore l'appel</summary>
              <input aria-label="Motif" value={note} onChange={(e) => setNote(e.target.value)} className={inputCls} placeholder="Motif (au moins 10 caractères)" />
              <div className="flex flex-wrap gap-2 mt-2">
                <Button variant="outline" disabled={note.length < 10} onClick={() => run(() => api.POST("/api/v1/calls/{call_id}/unsuccessful", { params: { path: { call_id: call.id } }, body: { reason: note } }), "Appel déclaré infructueux.")}>Infructueux</Button>
                <Button variant="danger" disabled={note.length < 10} onClick={() => run(() => api.POST("/api/v1/calls/{call_id}/cancel", { params: { path: { call_id: call.id } }, body: { reason: note } }), "Appel annulé.")}>Annuler</Button>
              </div>
            </details>
          )}
          <Msg />
        </div>
      )}
    </li>
  );
}

function Calls() {
  const q = useQuery({ queryKey: ["calls", "manage"], queryFn: async () => unwrap(await api.GET("/api/v1/calls/manage")) });
  return (
    <Card>
      <CardHeader icon={FileText} title="Appels à candidatures" />
      <p className="text-sm text-neutral-600 mb-3">Principe des quatre yeux : un appel est publié, et une attribution validée, par un superviseur autre que son auteur.</p>
      {q.isLoading && <Loading />}
      {q.isSuccess && !q.data.length && <Empty>Aucun appel. Préparez une terre puis rédigez un appel depuis son plan.</Empty>}
      <ul className="space-y-3">{q.data?.map((c) => <CallAdminCard key={c.id} call={c} />)}</ul>
    </Card>
  );
}

// --- Concessions -----------------------------------------------------------------------------

function ConcessionCard({ c }: { c: Concession }) {
  const { user } = useSession();
  const supervisor = user?.role === "state_supervisor";
  const { run, Msg } = useAction();
  const [panel, setPanel] = useState<"act" | "inspect" | "pay" | "end" | null>(null);
  const [act, setAct] = useState({ act_ref: "", act_date: new Date().toISOString().slice(0, 10), authority: "" });
  const [ins, setIns] = useState({ pct: "", compliant: true, note: "" });
  const [pay, setPay] = useState({ year: String(new Date().getFullYear()), amount: String(c.annual_fee_fcfa), receipt: "" });
  const [end, setEnd] = useState({ status: "retiree", reason: "defaut_mise_en_valeur", note: "" });
  const [review, setReview] = useState<ConcessionReview | undefined>(c.ai_review);
  const ai = useMutation({ mutationFn: async () => unwrap(await api.POST("/api/v1/concessions/{concession_id}/ai-review", { params: { path: { concession_id: c.id } } })) as unknown as ConcessionReview, onSuccess: setReview });
  const STATUS = { en_attente_acte: ["En attente de l'acte", "amber"], active: ["Active", "green"], retiree: ["Retirée", "red"], terminee: ["Terminée", "neutral"], annulee: ["Annulée", "neutral"] } as const;
  const [label, tone] = STATUS[c.status];
  const ASSESS = { conforme: ["Conforme", "green"], a_surveiller: ["À surveiller", "amber"], risque_de_defaut: ["Risque de défaut", "red"] } as const;
  return (
    <li className="p-4 border border-neutral-200 rounded-lg space-y-3 text-sm">
      <div className="flex flex-wrap justify-between gap-2">
        <span><span className="font-bold block text-base">{c.domain_name}</span>{c.farmer_name} · {c.crop_type} · {formatNumber(c.surface_hectares, 1)} ha</span>
        <Badge tone={tone}>{label}</Badge>
      </div>
      {c.status === "active" && (
        <p className="tabular-nums">Acte {c.act_ref} · mise en valeur {c.latest_mise_en_valeur_pct != null ? `${formatNumber(c.latest_mise_en_valeur_pct)} %` : "non inspectée"} · redevance due {formatFcfa(c.fees_due_fcfa)}, payée {formatFcfa(c.fees_paid_fcfa)}
          {c.mise_en_valeur_alert && <span className="text-red-700 font-semibold"> · délai de mise en valeur dépassé</span>}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {c.status === "en_attente_acte" && <Button onClick={() => setPanel(panel === "act" ? null : "act")}>Enregistrer l'acte officiel</Button>}
        {c.status === "active" && (
          <>
            <Button variant="outline" onClick={() => setPanel(panel === "inspect" ? null : "inspect")}>Inspection</Button>
            <Button variant="outline" onClick={() => setPanel(panel === "pay" ? null : "pay")}>Paiement</Button>
            <Button variant="soft" onClick={() => ai.mutate()} loading={ai.isPending}><Sparkles className="w-4 h-4" aria-hidden /> Analyse du suivi (IA)</Button>
            {supervisor && <Button variant="danger" onClick={() => setPanel(panel === "end" ? null : "end")}>Retrait ou fin</Button>}
          </>
        )}
      </div>
      {panel === "act" && (
        <div className="grid gap-2 sm:grid-cols-3 items-end p-3 rounded bg-neutral-50 border border-neutral-200">
          <Field id={`ar-${c.id}`} label="Référence de l'acte"><input id={`ar-${c.id}`} value={act.act_ref} onChange={(e) => setAct({ ...act, act_ref: e.target.value })} className={inputCls} /></Field>
          <Field id={`ad-${c.id}`} label="Date"><input id={`ad-${c.id}`} type="date" value={act.act_date} onChange={(e) => setAct({ ...act, act_date: e.target.value })} className={inputCls} /></Field>
          <Field id={`aa-${c.id}`} label="Autorité signataire"><input id={`aa-${c.id}`} value={act.authority} onChange={(e) => setAct({ ...act, authority: e.target.value })} className={inputCls} placeholder="Préfecture de…" /></Field>
          <Button className="sm:col-span-3" disabled={act.act_ref.length < 3 || act.authority.length < 3} onClick={() => run(() => api.POST("/api/v1/concessions/{concession_id}/official-act", { params: { path: { concession_id: c.id } }, body: act }), "Acte enregistré : la concession est active.")}>Activer la concession</Button>
        </div>
      )}
      {panel === "inspect" && (
        <div className="grid gap-2 sm:grid-cols-3 items-end p-3 rounded bg-neutral-50 border border-neutral-200">
          <Field id={`ip-${c.id}`} label="Mise en valeur constatée (%)"><input id={`ip-${c.id}`} inputMode="numeric" value={ins.pct} onChange={(e) => setIns({ ...ins, pct: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <label className="flex items-center gap-2 min-h-11"><input type="checkbox" className="w-5 h-5 accent-emerald-800" checked={ins.compliant} onChange={(e) => setIns({ ...ins, compliant: e.target.checked })} /> Conforme au cahier des charges</label>
          <Field id={`in-${c.id}`} label="Constat"><input id={`in-${c.id}`} value={ins.note} onChange={(e) => setIns({ ...ins, note: e.target.value })} className={inputCls} /></Field>
          <Button className="sm:col-span-3" disabled={!ins.pct || ins.note.length < 5} onClick={() => run(() => api.POST("/api/v1/concessions/{concession_id}/inspections", { params: { path: { concession_id: c.id } }, body: { mise_en_valeur_pct: Number(ins.pct), compliant: ins.compliant, note: ins.note } }), "Inspection enregistrée.")}>Enregistrer l'inspection</Button>
        </div>
      )}
      {panel === "pay" && (
        <div className="grid gap-2 sm:grid-cols-3 items-end p-3 rounded bg-neutral-50 border border-neutral-200">
          <Field id={`py-${c.id}`} label="Année"><input id={`py-${c.id}`} inputMode="numeric" value={pay.year} onChange={(e) => setPay({ ...pay, year: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <Field id={`pa-${c.id}`} label="Montant (FCFA)"><input id={`pa-${c.id}`} inputMode="numeric" value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <Field id={`pr-${c.id}`} label="N° de quittance"><input id={`pr-${c.id}`} value={pay.receipt} onChange={(e) => setPay({ ...pay, receipt: e.target.value })} className={inputCls} /></Field>
          <Button className="sm:col-span-3" disabled={pay.receipt.length < 3 || !pay.amount} onClick={() => run(() => api.POST("/api/v1/concessions/{concession_id}/payments", { params: { path: { concession_id: c.id } }, body: { year: Number(pay.year), amount_fcfa: Number(pay.amount), receipt_ref: pay.receipt } }), "Paiement enregistré.")}>Enregistrer le paiement</Button>
        </div>
      )}
      {panel === "end" && (
        <div className="grid gap-2 sm:grid-cols-3 items-end p-3 rounded bg-red-50 border border-red-200">
          <Field id={`es-${c.id}`} label="Décision"><select id={`es-${c.id}`} value={end.status} onChange={(e) => setEnd({ ...end, status: e.target.value })} className={inputCls}><option value="retiree">Retrait</option><option value="terminee">Fin normale</option></select></Field>
          <Field id={`er-${c.id}`} label="Motif"><select id={`er-${c.id}`} value={end.reason} onChange={(e) => setEnd({ ...end, reason: e.target.value })} className={inputCls}>
            <option value="defaut_mise_en_valeur">Défaut de mise en valeur</option><option value="non_paiement">Non-paiement</option><option value="manquement_cahier_des_charges">Manquement au cahier des charges</option>
            <option value="fin_de_contrat">Fin de contrat</option><option value="renonciation">Renonciation</option><option value="autre">Autre</option></select></Field>
          <Field id={`en-${c.id}`} label="Motivation"><input id={`en-${c.id}`} value={end.note} onChange={(e) => setEnd({ ...end, note: e.target.value })} className={inputCls} /></Field>
          <Button variant="danger" className="sm:col-span-3" disabled={end.note.length < 5} onClick={() => window.confirm("Confirmer la décision ? La terre redeviendra disponible.") && run(() => api.POST("/api/v1/concessions/{concession_id}/termination", { params: { path: { concession_id: c.id } }, body: end as never }), "Décision enregistrée.")}>Confirmer</Button>
        </div>
      )}
      {review && (
        <div className="p-3 rounded border border-emerald-200 bg-emerald-50/40 space-y-1">
          <p className="flex items-center gap-2"><strong>Évaluation :</strong> <Badge tone={ASSESS[review.assessment][1]}>{ASSESS[review.assessment][0]}</Badge></p>
          {!!review.findings.length && <p><strong>Constats :</strong> {review.findings.join(" ; ")}</p>}
          {!!review.early_warnings.length && <p><strong>Alertes précoces :</strong> {review.early_warnings.join(" ; ")}</p>}
          {!!review.recommended_actions.length && <p><strong>Actions proposées :</strong> {review.recommended_actions.join(" ; ")}</p>}
          {!!review.next_inspection_focus.length && <p><strong>À vérifier à la prochaine inspection :</strong> {review.next_inspection_focus.join(" ; ")}</p>}
          <p className="text-xs text-neutral-500">Analyse proposée par l'IA : la décision reste celle du superviseur.</p>
        </div>
      )}
      {ai.isError && <Alert tone="error">{(ai.error as Error).message}</Alert>}
      <Msg />
    </li>
  );
}

function Concessions() {
  const q = useQuery({ queryKey: ["concessions", "all"], queryFn: async () => unwrap(await api.GET("/api/v1/concessions")) as unknown as Concession[] });
  return (
    <Card>
      <CardHeader icon={Landmark} title="Concessions" />
      {q.isLoading && <Loading />}
      {q.isSuccess && !q.data.length && <Empty>Aucune concession.</Empty>}
      <ul className="space-y-3">{q.data?.map((c) => <ConcessionCard key={c.id} c={c} />)}</ul>
    </Card>
  );
}

// --- Exploitants ----------------------------------------------------------------------------

function Ranking() {
  const [f, setF] = useState({ department: "", crop: "", eligible_only: false });
  const q = useQuery({
    queryKey: ["ranking", f],
    queryFn: async () => unwrap(await api.GET("/api/v1/state/farmers/performance", { params: { query: { department: f.department || undefined, crop: f.crop || undefined, eligible_only: f.eligible_only || undefined, limit: 50 } } })) as unknown as (Performance & { rank: number; full_name?: string })[],
  });
  return (
    <Card>
      <CardHeader icon={Users} title="Classement des exploitants" />
      <div className="grid gap-3 sm:grid-cols-3 mb-4 items-end">
        <Field id="rk-d" label="Département"><select id="rk-d" value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} className={inputCls}><option value="">Tous</option>{DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}</select></Field>
        <Field id="rk-c" label="Culture"><input id="rk-c" value={f.crop} onChange={(e) => setF({ ...f, crop: e.target.value })} className={inputCls} placeholder="Toutes" /></Field>
        <label className="flex items-center gap-2 min-h-11 text-sm"><input type="checkbox" className="w-5 h-5 accent-emerald-800" checked={f.eligible_only} onChange={(e) => setF({ ...f, eligible_only: e.target.checked })} /> Éligibles seulement</label>
      </div>
      {q.isLoading && <Loading />}
      <div className="overflow-x-auto">
        <table className="w-full text-sm [&_td]:whitespace-nowrap">
          <thead><tr className="text-left text-neutral-500 border-b border-neutral-200"><th className="py-2 pr-3 font-semibold">Rang</th><th className="py-2 pr-3 font-semibold">Exploitant</th><th className="py-2 pr-3 font-semibold">Cultures</th><th className="py-2 pr-3 font-semibold text-right">Surface vérifiée</th><th className="py-2 pr-3 font-semibold text-right">Saisons</th><th className="py-2 pr-3 font-semibold text-right">Score</th><th className="py-2 font-semibold">Éligible</th></tr></thead>
          <tbody className="tabular-nums">
            {q.data?.map((r) => (
              <tr key={r.npi} className="border-b border-neutral-100">
                <td className="py-2 pr-3">{r.rank}</td><td className="py-2 pr-3 font-semibold font-sans">{r.full_name}</td><td className="py-2 pr-3 font-sans">{r.stats.crops.join(", ")}</td>
                <td className="py-2 pr-3 text-right">{formatNumber(r.stats.verified_surface_ha, 2)} ha</td><td className="py-2 pr-3 text-right">{r.stats.seasons}</td>
                <td className="py-2 pr-3 text-right font-bold">{formatNumber(r.score, 1)}</td><td className="py-2">{r.eligible ? <Badge tone="green">Oui</Badge> : <Badge>Non</Badge>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-neutral-500 mt-3">Score : productivité comparée aux voisins (40 %), fiabilité des prévisions, régularité, conformité et ventes (15 % chacun). Seules les parcelles vérifiées comptent.</p>
    </Card>
  );
}

type Tab = "terres" | "appels" | "concessions" | "exploitants";

export function AgentLands() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("onglet") as Tab) ?? "terres";
  const tabs: [Tab, string][] = [["terres", "Terres"], ["appels", "Appels"], ["concessions", "Concessions"], ["exploitants", "Exploitants"]];
  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight flex items-center gap-2"><Landmark className="w-5 h-5 text-emerald-800" aria-hidden /> Domaine privé de l'État</h1>
            <p className="text-sm text-neutral-600">Préparation des terres, appels à candidatures, concessions. L'acte officiel reste délivré par l'autorité compétente.</p>
          </div>
          <div role="tablist" className="flex gap-1 bg-neutral-100 p-1 rounded border border-neutral-200 overflow-x-auto max-w-full">
            {tabs.map(([t, l]) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setParams({ onglet: t })}
                      className={`min-h-10 px-3 rounded text-sm font-semibold whitespace-nowrap shrink-0 cursor-pointer ${tab === t ? "bg-white shadow-sm text-emerald-900" : "text-neutral-600"}`}>{l}</button>
            ))}
          </div>
        </div>
      </Card>
      {tab === "terres" && <Domains />}
      {tab === "appels" && <Calls />}
      {tab === "concessions" && <Concessions />}
      {tab === "exploitants" && <Ranking />}
    </div>
  );
}
