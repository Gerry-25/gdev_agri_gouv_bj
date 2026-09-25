import { api, apiErrorMessage, formatDate, formatHectares, formatNumber, useSession } from "@agri/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, BarChart3, FileText, Scale, Sparkles, Warehouse } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Alert, Badge, Button, Card, CardHeader, Empty, Loading } from "../../components/ui";
import { DEPARTMENTS } from "../../lib/benin";
import { unwrap } from "../../lib/queries";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";

function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm [&_td]:whitespace-nowrap">
        <thead><tr className="text-left text-neutral-500 border-b border-neutral-200">{head.map((h, i) => <th key={h} className={`py-2 pr-3 font-semibold ${i > 0 ? "text-right" : ""}`}>{h}</th>)}</tr></thead>
        <tbody className="tabular-nums">{children}</tbody>
      </table>
    </div>
  );
}

// --- Statistiques ------------------------------------------------------------------------

interface ZoneRow { department: string; commune?: string; parcels: number; surface_ha: number; estimated_production_kg: number; actual_production_kg: number; parcels_in_dispute: number; threats: number; critical: number }
interface CropRow { crop_type: string; parcels: number; surface_ha: number; estimated_production_kg: number; actual_production_kg: number; seasons: number; yield_kg_per_ha: number | null }
interface StockRow { product: string; department: string | null; in_stock_kg: number; lost_kg: number; loss_rate_pct: number; lots: number }

function Overview() {
  const [department, setDepartment] = useState("");
  const zones = useQuery({
    queryKey: ["state", "zones", department],
    queryFn: async () => unwrap(await api.GET("/api/v1/state/stats/zones", { params: { query: { level: department ? "commune" : "department", department: department || undefined } } })) as unknown as ZoneRow[],
  });
  const crops = useQuery({ queryKey: ["state", "crops", department], queryFn: async () => unwrap(await api.GET("/api/v1/state/stats/crops", { params: { query: { department: department || undefined } } })) as unknown as CropRow[] });
  const stocks = useQuery({ queryKey: ["state", "stocks"], queryFn: async () => unwrap(await api.GET("/api/v1/storage/overview")) as unknown as StockRow[] });
  const t = (kg: number) => formatNumber(kg / 1000, 1);
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader icon={BarChart3} title={department ? `Communes du département : ${department}` : "Par département"} action={
          <select aria-label="Département" value={department} onChange={(e) => setDepartment(e.target.value)} className="min-h-9 px-2 border border-neutral-300 rounded bg-white text-sm">
            <option value="">Tout le Bénin</option>{DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
          </select>} />
        {zones.isLoading && <Loading />}
        {zones.data && (
          <Table head={[department ? "Commune" : "Département", "Parcelles", "Surface", "Prévu par saison (t)", "Récolté, cumul (t)", "En litige", "Menaces (30 j)"]}>
            {zones.data.map((z) => (
              <tr key={`${z.department}-${z.commune}`} className="border-b border-neutral-100">
                <td className="py-2 pr-3 font-semibold font-sans">{department ? z.commune : <button type="button" onClick={() => setDepartment(z.department)} className="underline text-emerald-800 cursor-pointer">{z.department}</button>}</td>
                <td className="py-2 pr-3 text-right">{formatNumber(z.parcels)}</td>
                <td className="py-2 pr-3 text-right">{formatHectares(z.surface_ha)}</td>
                <td className="py-2 pr-3 text-right">{t(z.estimated_production_kg)}</td>
                <td className="py-2 pr-3 text-right">{t(z.actual_production_kg)}</td>
                <td className={`py-2 pr-3 text-right ${z.parcels_in_dispute ? "text-red-700 font-semibold" : ""}`}>{z.parcels_in_dispute}</td>
                <td className={`py-2 text-right ${z.critical ? "text-red-700 font-semibold" : ""}`}>{z.threats}{z.critical ? ` (${z.critical} crit.)` : ""}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card>
          <CardHeader icon={BarChart3} title="Par culture" />
          {crops.data && (
            <Table head={["Culture", "Surface", "Prévu par saison (t)", "Récolté, cumul (t)", "Rendement (kg/ha)"]}>
              {crops.data.map((c) => (
                <tr key={c.crop_type} className="border-b border-neutral-100">
                  <td className="py-2 pr-3 font-semibold font-sans">{c.crop_type}</td><td className="py-2 pr-3 text-right">{formatHectares(c.surface_ha)}</td>
                  <td className="py-2 pr-3 text-right">{t(c.estimated_production_kg)}</td><td className="py-2 pr-3 text-right">{t(c.actual_production_kg)}{c.seasons ? <span className="text-xs text-neutral-500"> · {c.seasons} saison{c.seasons > 1 ? "s" : ""}</span> : null}</td>
                  <td className="py-2 text-right">{c.yield_kg_per_ha ? formatNumber(c.yield_kg_per_ha) : "—"}</td>
                </tr>
              ))}
            </Table>
          )}
          <p className="text-xs text-neutral-500 mt-2">Rendement : récoltes déclarées rapportées à la surface récoltée à chaque saison.</p>
        </Card>
        <Card>
          <CardHeader icon={Warehouse} title="Stocks et pertes déclarés" />
          {stocks.data && !stocks.data.length && <Empty>Aucun stock déclaré.</Empty>}
          {!!stocks.data?.length && (
            <Table head={["Produit", "Département", "En stock (t)", "Pertes"]}>
              {stocks.data.map((s, i) => (
                <tr key={i} className="border-b border-neutral-100">
                  <td className="py-2 pr-3 font-semibold font-sans capitalize">{s.product}</td><td className="py-2 pr-3 text-right font-sans">{s.department ?? "—"}</td>
                  <td className="py-2 pr-3 text-right">{t(s.in_stock_kg)}</td>
                  <td className={`py-2 text-right ${s.loss_rate_pct >= 10 ? "text-red-700 font-semibold" : ""}`}>{formatNumber(s.loss_rate_pct, 1)} %</td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>
    </div>
  );
}

// --- Litiges ---------------------------------------------------------------------------

interface Summary { neutral_summary: string; chronology: string[]; established_facts: string[]; points_of_contention: string[]; missing_information: string[];
  mediation_questions: string[]; suggested_next_steps: string[]; disclaimer?: string }

const DSTATUS = { ouvert: ["Ouvert", "red"], en_mediation: ["En médiation", "amber"], resolu: ["Résolu", "green"], rejete: ["Rejeté", "neutral"] } as const;
const DTYPE: Record<string, string> = { chevauchement: "Chevauchement entre parcelles", chevauchement_domaine_etat: "Empiètement sur une terre de l'État",
  revendication: "Revendication de propriété", limite: "Désaccord sur une limite", autre: "Autre litige" };

function SummaryBlock({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return <div><h4 className="text-sm font-bold">{title}</h4><ul className="list-disc pl-5 text-sm space-y-0.5">{items.map((i) => <li key={i}>{i}</li>)}</ul></div>;
}

function DisputeItem({ d, onDecided }: { d: { id: string; type: string; status: keyof typeof DSTATUS; reason: string; commune?: string | null; department?: string | null;
  overlap_area_m2?: number | null; land_ids: string[]; created_at: string; resolution_note?: string | null; ai_summary?: unknown }; onDecided: (text: string) => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [decision, setDecision] = useState({ status: "en_mediation", note: "" });
  const summary = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/lands/disputes/{dispute_id}/ai-summary", { params: { path: { dispute_id: d.id } } })) as unknown as Summary,
  });
  const decide = useMutation({
    mutationFn: async () => unwrap(await api.PATCH("/api/v1/lands/disputes/{dispute_id}", { params: { path: { dispute_id: d.id } }, body: { status: decision.status as never, resolution_note: decision.note } })),
    onSuccess: () => {
      const where = { en_mediation: "« En médiation »", resolu: "« Résolus »", rejete: "« Rejetés »" }[decision.status];
      onDecided(`Décision enregistrée et communiquée aux parties (${d.commune}). Le litige est désormais dans la liste ${where}.`);
      qc.invalidateQueries({ queryKey: ["disputes"] });
    },
  });
  const [label, tone] = DSTATUS[d.status];
  const s = summary.data ?? (d.ai_summary as Summary | undefined);
  const closed = d.status === "resolu" || d.status === "rejete";
  return (
    <li className="border border-neutral-200 rounded-lg">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="w-full p-3.5 text-left flex flex-wrap items-start justify-between gap-2 cursor-pointer">
        <span className="min-w-0">
          <span className="font-semibold block">{DTYPE[d.type] ?? d.type}</span>
          <span className="text-sm text-neutral-600">{d.commune} ({d.department}) · ouvert le {formatDate(d.created_at)}{d.overlap_area_m2 ? ` · ${formatNumber(d.overlap_area_m2)} m² en cause` : ""}</span>
        </span>
        <Badge tone={tone}>{label}</Badge>
      </button>
      {open && (
        <div className="px-3.5 pb-4 space-y-4 border-t border-neutral-100 pt-3">
          <p className="text-sm">{d.reason}</p>
          <div className="flex flex-wrap gap-2 text-sm">{d.land_ids.map((id, i) => <Link key={id} to={`/cadastre/${id}`} className="underline text-emerald-800">Voir la parcelle {i + 1}</Link>)}</div>
          {!s ? (
            <Button variant="soft" onClick={() => summary.mutate()} loading={summary.isPending}><Sparkles className="w-4 h-4" aria-hidden /> Préparer une synthèse neutre (IA)</Button>
          ) : (
            <div className="p-3 rounded-lg border border-emerald-200 bg-emerald-50/40 space-y-3">
              <p className="text-sm font-semibold">{s.neutral_summary}</p>
              <SummaryBlock title="Chronologie" items={s.chronology} />
              <SummaryBlock title="Faits établis" items={s.established_facts} />
              <SummaryBlock title="Points de désaccord" items={s.points_of_contention} />
              <SummaryBlock title="Pièces à demander" items={s.missing_information} />
              <SummaryBlock title="Questions pour la médiation" items={s.mediation_questions} />
              <SummaryBlock title="Suites possibles" items={s.suggested_next_steps} />
              <p className="text-xs text-neutral-500">Synthèse anonymisée proposée par l'IA : les parties y sont désignées « partie A », « partie B ». Elle ne remplace ni l'enquête ni la décision.</p>
            </div>
          )}
          {summary.isError && <Alert tone="error">{(summary.error as Error).message}</Alert>}
          {closed ? <p className="text-sm text-neutral-600">Décision : {d.resolution_note}</p> : (
            <form onSubmit={(e) => { e.preventDefault(); decide.mutate(); }} className="grid gap-3 sm:grid-cols-3 items-end">
              <div><label htmlFor={`ds-${d.id}`} className="block text-sm font-semibold mb-1">Décision</label>
                <select id={`ds-${d.id}`} value={decision.status} onChange={(e) => setDecision({ ...decision, status: e.target.value })} className={inputCls}>
                  <option value="en_mediation">Passer en médiation</option><option value="resolu">Résolu</option><option value="rejete">Rejeté</option>
                </select></div>
              <div className="sm:col-span-2"><label htmlFor={`dn-${d.id}`} className="block text-sm font-semibold mb-1">Motif (communiqué aux parties)</label>
                <input id={`dn-${d.id}`} value={decision.note} onChange={(e) => setDecision({ ...decision, note: e.target.value })} className={inputCls} placeholder="Ex. : bornage contradictoire réalisé le 12/10" /></div>
              <Button type="submit" className="sm:col-span-3" loading={decide.isPending} disabled={decision.note.trim().length < 5}>Enregistrer la décision</Button>
              {decide.isError && <div className="sm:col-span-3"><Alert tone="error">{(decide.error as Error).message}</Alert></div>}
            </form>
          )}
        </div>
      )}
    </li>
  );
}

function Disputes() {
  const [status, setStatus] = useState<"ouvert" | "en_mediation" | "resolu" | "rejete">("ouvert");
  const q = useQuery({ queryKey: ["disputes", status], queryFn: async () => unwrap(await api.GET("/api/v1/lands/disputes", { params: { query: { status, limit: 100 } } })) });
  const [notice, setNotice] = useState<string | null>(null);
  return (
    <Card>
      <CardHeader icon={Scale} title="Litiges fonciers" action={
        <select aria-label="Statut" value={status} onChange={(e) => setStatus(e.target.value as typeof status)} className="min-h-9 px-2 border border-neutral-300 rounded bg-white text-sm">
          <option value="ouvert">Ouverts</option><option value="en_mediation">En médiation</option><option value="resolu">Résolus</option><option value="rejete">Rejetés</option>
        </select>} />
      {q.isLoading && <Loading />}
      {notice && <div className="mb-3"><Alert tone="success">{notice}</Alert></div>}
      {q.isSuccess && !q.data.length && <Empty>Aucun litige dans cette catégorie.</Empty>}
      <ul className="space-y-2">{q.data?.map((d) => <DisputeItem key={d.id} d={d as never} onDecided={setNotice} />)}</ul>
    </Card>
  );
}

// --- Transferts --------------------------------------------------------------------------

const REASONS: Record<string, string> = { vente: "Vente", heritage: "Héritage", donation: "Donation", autre: "Autre" };

function Transfers() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["transfers", "pending"], queryFn: async () => unwrap(await api.GET("/api/v1/lands/transfers", { params: { query: { status: "en_attente" } } })) });
  const [notes, setNotes] = useState<Record<string, string>>({});
  const decide = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: "approuve" | "rejete" }) =>
      unwrap(await api.PATCH("/api/v1/lands/transfers/{transfer_id}", { params: { path: { transfer_id: id } }, body: { status, note: notes[id] || undefined } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["transfers"] }),
  });
  return (
    <Card>
      <CardHeader icon={ArrowLeftRight} title="Transferts de propriété à traiter" />
      {q.isLoading && <Loading />}
      {q.isSuccess && !q.data.length && <Empty>Aucun transfert en attente.</Empty>}
      <ul className="space-y-3">
        {q.data?.map((t) => (
          <li key={t.id} className="p-3.5 border border-neutral-200 rounded-lg space-y-2">
            <div className="flex flex-wrap justify-between gap-2">
              <span className="font-semibold">{REASONS[t.reason] ?? t.reason} · {t.commune} ({t.department})</span>
              <span className="text-sm text-neutral-500">demandé le {formatDate(t.created_at)}</span>
            </div>
            <p className="text-sm tabular-nums">NPI {t.from_npi} → NPI {t.new_owner_npi}</p>
            {t.note && <p className="text-sm text-neutral-600">{t.note}</p>}
            <Link to={`/cadastre/${t.land_id}`} className="text-sm underline text-emerald-800">Voir la parcelle</Link>
            <label htmlFor={`tn-${t.id}`} className="sr-only">Note</label>
            <input id={`tn-${t.id}`} value={notes[t.id] ?? ""} onChange={(e) => setNotes({ ...notes, [t.id]: e.target.value })} className={inputCls} placeholder="Pièces vérifiées (acte, témoins…)" />
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => decide.mutate({ id: t.id, status: "approuve" })} loading={decide.isPending}>Approuver</Button>
              <Button variant="danger" onClick={() => decide.mutate({ id: t.id, status: "rejete" })}>Rejeter</Button>
            </div>
          </li>
        ))}
      </ul>
      {decide.isError && <div className="mt-3"><Alert tone="error">{(decide.error as Error).message}</Alert></div>}
    </Card>
  );
}

// --- Note hebdomadaire ----------------------------------------------------------------------

interface Report { id: string; scope: string; created_at: string; disclaimer?: string; report: { title: string; highlights: string[]; sanitary_situation: string; land_situation: string;
  market_situation: string; priority_actions: { action: string; zone: string; reason: string }[]; watch_points: string[] } }

function ReportView({ r }: { r: Report }) {
  const x = r.report;
  return (
    <article className="space-y-3 text-sm">
      <header><h3 className="text-base font-bold">{x.title}</h3><p className="text-xs text-neutral-500">{r.scope === "national" ? "National" : r.scope} · {formatDate(r.created_at)}</p></header>
      <ul className="list-disc pl-5 space-y-0.5">{x.highlights.map((h) => <li key={h}>{h}</li>)}</ul>
      <p><strong>Situation sanitaire : </strong>{x.sanitary_situation}</p>
      <p><strong>Foncier : </strong>{x.land_situation}</p>
      <p><strong>Marché : </strong>{x.market_situation}</p>
      {!!x.priority_actions.length && (
        <div><h4 className="font-bold">Actions prioritaires</h4>
          <ol className="list-decimal pl-5 space-y-1">{x.priority_actions.map((a) => <li key={a.action + a.zone}><strong>{a.action}</strong> ({a.zone}) : {a.reason}</li>)}</ol></div>
      )}
      {!!x.watch_points.length && <p><strong>Points de vigilance : </strong>{x.watch_points.join(" ; ")}</p>}
      <p className="text-xs text-neutral-500">Note rédigée par l'IA à partir des seules données de la plateforme.</p>
    </article>
  );
}

function Weekly() {
  const qc = useQueryClient();
  const [department, setDepartment] = useState("");
  const list = useQuery({ queryKey: ["reports"], queryFn: async () => unwrap(await api.GET("/api/v1/state/reports")) as unknown as Report[] });
  const make = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/v1/state/reports/weekly", { params: { query: { department: department || undefined } } });
      if (error) throw new Error(apiErrorMessage(error));
      return data as unknown as Report;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports"] }),
  });
  const latest = make.data ?? list.data?.[0];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
      <Card className="lg:col-span-4 space-y-3">
        <CardHeader icon={FileText} title="Note de la semaine" />
        <label htmlFor="rdep" className="block text-sm font-semibold">Périmètre</label>
        <select id="rdep" value={department} onChange={(e) => setDepartment(e.target.value)} className={inputCls}><option value="">National</option>{DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}</select>
        <Button className="w-full" onClick={() => make.mutate()} loading={make.isPending}><Sparkles className="w-4 h-4" aria-hidden /> Rédiger la note (IA)</Button>
        {make.isError && <Alert tone="error">{(make.error as Error).message}</Alert>}
        {!!list.data?.length && (
          <div className="pt-3 border-t border-neutral-100">
            <p className="text-sm font-semibold mb-1">Notes précédentes</p>
            <ul className="text-sm text-neutral-600 space-y-1">{list.data.slice(0, 8).map((r) => <li key={r.id}>{formatDate(r.created_at)} · {r.scope === "national" ? "National" : r.scope}</li>)}</ul>
          </div>
        )}
      </Card>
      <Card className="lg:col-span-8">{latest ? <ReportView r={latest} /> : <Empty>Aucune note rédigée pour le moment.</Empty>}</Card>
    </div>
  );
}

type Tab = "stats" | "litiges" | "transferts" | "note";

export function SupervisionPage() {
  const { user } = useSession();
  const [tab, setTab] = useState<Tab>("stats");
  const tabs: [Tab, string][] = [["stats", "Statistiques"], ["litiges", "Litiges"], ["transferts", "Transferts"], ["note", "Note hebdomadaire"]];
  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Supervision</h1>
            <p className="text-sm text-neutral-600">{user?.role === "state_supervisor" ? "Superviseur" : "Agent de l'État"} · suivi du territoire, du foncier et des décisions.</p>
          </div>
          <div role="tablist" className="flex gap-1 bg-neutral-100 p-1 rounded border border-neutral-200 overflow-x-auto max-w-full">
            {tabs.map(([t, label]) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                      className={`min-h-10 px-3 rounded text-sm font-semibold cursor-pointer whitespace-nowrap shrink-0 ${tab === t ? "bg-white shadow-sm text-emerald-900" : "text-neutral-600"}`}>{label}</button>
            ))}
          </div>
        </div>
      </Card>
      {tab === "stats" && <Overview />}
      {tab === "litiges" && <Disputes />}
      {tab === "transferts" && <Transfers />}
      {tab === "note" && <Weekly />}
    </div>
  );
}
