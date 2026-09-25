import { api, apiErrorMessage, enqueue, formatDate, formatNumber, newClientRef } from "@agri/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, CloudOff, PackageCheck, Plus, Sparkles, Warehouse } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Alert, Badge, Button, Card, CardHeader, Empty, Loading } from "../../components/ui";
import { COMMON_CROPS } from "../../lib/benin";
import { unwrap, useMyLands } from "../../lib/queries";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";

interface Risk { level: "faible" | "moyen" | "eleve"; factors: string[]; safe_moisture_pct: number | null; check_every_days: number; next_check_date: string; stored_days: number }
interface Lot {
  id: string; product: string; quantity_kg: number; initial_quantity_kg: number; harvest_date: string; storage_method: string;
  last_moisture_pct?: number | null; status: string; commune?: string | null; risk: Risk | null; checks: unknown[]; quantity_lost_kg?: number;
}
interface Advice {
  simple_summary: string; immediate_actions: string[]; check_schedule: string; sell_or_store: "vendre_maintenant" | "vendre_en_partie" | "stocker";
  sell_or_store_reasoning: string; warrantage_note: string; warnings: string[];
  prices: { recent_avg_fcfa_kg: number | null; trend: string | null; observations: number };
}

const METHODS: [string, string][] = [
  ["sac_hermetique", "Sacs hermétiques (type PICS)"], ["sac_polypropylene", "Sacs en polypropylène"], ["grenier_traditionnel", "Grenier traditionnel"],
  ["magasin_ventile", "Magasin ventilé"], ["fut_hermetique", "Fût hermétique"], ["autre", "Autre"],
];
const METHOD_LABEL = Object.fromEntries(METHODS);
const RISK = { faible: ["Risque faible", "green"], moyen: ["Risque moyen", "amber"], eleve: ["Risque élevé", "red"] } as const;
const DECISION = { vendre_maintenant: "Vendre maintenant", vendre_en_partie: "Vendre une partie", stocker: "Continuer à stocker" };

function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return <div><label htmlFor={id} className="block text-sm font-semibold mb-1">{label}</label>{children}</div>;
}

function NewLotForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const lands = useMyLands();
  const [f, setF] = useState({ product: "", quantity_kg: "", harvest_date: "", storage_method: "sac_polypropylene", moisture_pct: "", land_id: "" });
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const body = {
      product: f.product, quantity_kg: Number(f.quantity_kg), harvest_date: f.harvest_date, storage_method: f.storage_method,
      moisture_pct: f.moisture_pct ? Number(f.moisture_pct.replace(",", ".")) : undefined, land_id: f.land_id || undefined, client_ref: newClientRef(),
    };
    try {
      const { error: err } = await api.POST("/api/v1/storage/lots", { body: body as never });
      if (err) return setError(apiErrorMessage(err));
      qc.invalidateQueries({ queryKey: ["stocks"] });
      onDone();
    } catch {
      await enqueue("stock", `Stock de ${f.product.toLowerCase()} (${f.quantity_kg} kg)`, body);
      setQueued(true);
    } finally {
      setBusy(false);
    }
  };
  if (queued) return <Alert tone="warning"><span className="flex gap-2"><CloudOff className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />Stock gardé sur le téléphone : il sera enregistré au retour du réseau.</span></Alert>;
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2" noValidate>
      <Field id="sp" label="Produit"><input id="sp" list="sprods" value={f.product} onChange={set("product")} className={inputCls} /><datalist id="sprods">{COMMON_CROPS.map((c) => <option key={c} value={c} />)}</datalist></Field>
      <Field id="sq" label="Quantité (kg)"><input id="sq" inputMode="numeric" value={f.quantity_kg} onChange={(e) => setF({ ...f, quantity_kg: e.target.value.replace(/\D/g, "") })} className={`${inputCls} tabular-nums`} /></Field>
      <Field id="sd" label="Date de récolte"><input id="sd" type="date" max={new Date().toISOString().slice(0, 10)} value={f.harvest_date} onChange={set("harvest_date")} className={inputCls} /></Field>
      <Field id="sm" label="Comment est-il stocké ?"><select id="sm" value={f.storage_method} onChange={set("storage_method")} className={inputCls}>{METHODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
      <Field id="sh" label="Humidité mesurée en % (si vous avez un humidimètre)"><input id="sh" inputMode="decimal" value={f.moisture_pct} onChange={set("moisture_pct")} className={`${inputCls} tabular-nums`} /></Field>
      {!!lands.data?.length && (
        <Field id="sl" label="Parcelle d'origine (facultatif)"><select id="sl" value={f.land_id} onChange={set("land_id")} className={inputCls}><option value="">Aucune</option>{lands.data.map((l) => <option key={l.id} value={l.id}>{l.crop_type} · {l.locality ?? l.commune}</option>)}</select></Field>
      )}
      {error && <div className="sm:col-span-2"><Alert tone="error">{error}</Alert></div>}
      <Button type="submit" className="sm:col-span-2" loading={busy} disabled={f.product.trim().length < 2 || !f.quantity_kg || !f.harvest_date}>Enregistrer le stock</Button>
    </form>
  );
}

function LotCard({ lot }: { lot: Lot }) {
  const qc = useQueryClient();
  const [panel, setPanel] = useState<"check" | "close" | null>(null);
  const [check, setCheck] = useState({ moisture_pct: "", insects_seen: false, mold_seen: false, quantity_kg: "" });
  const [close, setClose] = useState({ status: "vendu", quantity_lost_kg: "" });
  const refresh = () => qc.invalidateQueries({ queryKey: ["stocks"] });
  const advice = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/storage/lots/{lot_id}/advice", { params: { path: { lot_id: lot.id } } })) as unknown as Advice,
  });
  const saveCheck = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/storage/lots/{lot_id}/checks", { params: { path: { lot_id: lot.id } }, body: {
      moisture_pct: check.moisture_pct ? Number(check.moisture_pct.replace(",", ".")) : undefined, insects_seen: check.insects_seen, mold_seen: check.mold_seen,
      quantity_kg: check.quantity_kg ? Number(check.quantity_kg) : undefined,
    } })),
    onSuccess: () => { setPanel(null); refresh(); },
  });
  const closeLot = useMutation({
    mutationFn: async () => unwrap(await api.PATCH("/api/v1/storage/lots/{lot_id}/status", { params: { path: { lot_id: lot.id } }, body: {
      status: close.status as never, quantity_lost_kg: close.quantity_lost_kg ? Number(close.quantity_lost_kg) : undefined,
    } })),
    onSuccess: refresh,
  });
  const risk = lot.risk;
  const [riskLabel, riskTone] = risk ? RISK[risk.level] : ["", "neutral" as const];
  const due = risk && risk.next_check_date <= new Date().toISOString().slice(0, 10);

  return (
    <li className={`p-4 rounded-lg border space-y-3 ${risk?.level === "eleve" ? "border-red-300 bg-red-50/30" : risk?.level === "moyen" ? "border-amber-300 bg-amber-50/30" : "border-neutral-200"}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-bold">{lot.product} · <span className="tabular-nums">{formatNumber(lot.quantity_kg)} kg</span></h3>
          <p className="text-sm text-neutral-600">{METHOD_LABEL[lot.storage_method]} · récolté le {formatDate(lot.harvest_date)}{risk ? ` (${risk.stored_days} j)` : ""}</p>
        </div>
        {risk && <Badge tone={riskTone}>{riskLabel}</Badge>}
      </div>
      {risk && (
        <>
          <ul className="text-sm text-neutral-700 list-disc pl-5 space-y-0.5">{risk.factors.map((f) => <li key={f}>{f}</li>)}</ul>
          <p className={`text-sm ${due ? "font-bold text-red-700" : "text-neutral-600"}`}>
            {due ? "Contrôle à faire maintenant" : `Prochain contrôle le ${formatDate(risk.next_check_date)}`} (tous les {risk.check_every_days} jours)
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant={due ? "primary" : "outline"} onClick={() => setPanel(panel === "check" ? null : "check")}><ClipboardCheck className="w-4 h-4" aria-hidden /> Faire un contrôle</Button>
            <Button variant="soft" onClick={() => advice.mutate()} loading={advice.isPending}><Sparkles className="w-4 h-4" aria-hidden /> Vendre ou stocker ?</Button>
            <Button variant="ghost" onClick={() => setPanel(panel === "close" ? null : "close")}><PackageCheck className="w-4 h-4" aria-hidden /> Clore ce stock</Button>
          </div>
        </>
      )}
      {!risk && <p className="text-sm text-neutral-600">Stock clos ({lot.status}){lot.quantity_lost_kg ? ` · ${formatNumber(lot.quantity_lost_kg)} kg perdus` : ""}.</p>}

      {panel === "check" && (
        <form onSubmit={(e) => { e.preventDefault(); saveCheck.mutate(); }} className="grid gap-3 sm:grid-cols-2 p-3 rounded border border-neutral-200 bg-white">
          <Field id={`cm-${lot.id}`} label="Humidité (%)"><input id={`cm-${lot.id}`} inputMode="decimal" value={check.moisture_pct} onChange={(e) => setCheck({ ...check, moisture_pct: e.target.value })} className={inputCls} /></Field>
          <Field id={`cq-${lot.id}`} label="Quantité restante (kg)"><input id={`cq-${lot.id}`} inputMode="numeric" value={check.quantity_kg} onChange={(e) => setCheck({ ...check, quantity_kg: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <label className="flex items-center gap-2 min-h-11 text-sm"><input type="checkbox" className="w-5 h-5 accent-emerald-800" checked={check.insects_seen} onChange={(e) => setCheck({ ...check, insects_seen: e.target.checked })} /> J'ai vu des insectes</label>
          <label className="flex items-center gap-2 min-h-11 text-sm"><input type="checkbox" className="w-5 h-5 accent-emerald-800" checked={check.mold_seen} onChange={(e) => setCheck({ ...check, mold_seen: e.target.checked })} /> J'ai vu des moisissures</label>
          <Button type="submit" className="sm:col-span-2" loading={saveCheck.isPending}>Enregistrer le contrôle</Button>
        </form>
      )}
      {panel === "close" && (
        <form onSubmit={(e) => { e.preventDefault(); closeLot.mutate(); }} className="grid gap-3 sm:grid-cols-2 p-3 rounded border border-neutral-200 bg-white">
          <Field id={`xs-${lot.id}`} label="Ce stock a été"><select id={`xs-${lot.id}`} value={close.status} onChange={(e) => setClose({ ...close, status: e.target.value })} className={inputCls}>
            <option value="vendu">Vendu</option><option value="consomme">Consommé</option><option value="perdu">Perdu (abîmé)</option><option value="transfere">Donné ou transféré</option></select></Field>
          <Field id={`xl-${lot.id}`} label="Quantité perdue (kg)"><input id={`xl-${lot.id}`} inputMode="numeric" value={close.quantity_lost_kg} onChange={(e) => setClose({ ...close, quantity_lost_kg: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <Button type="submit" className="sm:col-span-2" loading={closeLot.isPending}>Clore le stock</Button>
        </form>
      )}
      {(saveCheck.isError || closeLot.isError || advice.isError) && <Alert tone="error">{((saveCheck.error ?? closeLot.error ?? advice.error) as Error).message}</Alert>}

      {advice.data && (
        <div className="p-3 rounded-lg border border-emerald-200 bg-white space-y-2 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-base font-bold text-emerald-950">{DECISION[advice.data.sell_or_store]}</span>
            {advice.data.prices.recent_avg_fcfa_kg && (
              <span className="text-neutral-600 tabular-nums">Prix récent : {formatNumber(advice.data.prices.recent_avg_fcfa_kg)} FCFA/kg{advice.data.prices.trend ? ` (${advice.data.prices.trend})` : ""}</span>
            )}
          </div>
          <p className="font-semibold">{advice.data.simple_summary}</p>
          <p className="text-neutral-700">{advice.data.sell_or_store_reasoning}</p>
          <ol className="list-decimal pl-5 space-y-0.5">{advice.data.immediate_actions.map((a) => <li key={a}>{a}</li>)}</ol>
          <p className="text-neutral-600"><strong>Contrôles : </strong>{advice.data.check_schedule}</p>
          {advice.data.warrantage_note && <p className="text-neutral-600"><strong>Warrantage : </strong>{advice.data.warrantage_note}</p>}
          {advice.data.warnings.map((w) => <Alert key={w} tone="warning">{w}</Alert>)}
          <p className="text-xs text-neutral-500">Conseil proposé par l'IA. N'utilisez jamais de produit de conservation non homologué.</p>
        </div>
      )}
    </li>
  );
}

export function StoragePage() {
  const [adding, setAdding] = useState(false);
  const q = useQuery({ queryKey: ["stocks", "me"], queryFn: async () => unwrap(await api.GET("/api/v1/storage/lots/me")) as unknown as Lot[] });
  const active = (q.data ?? []).filter((l) => l.status === "en_stock");
  const closed = (q.data ?? []).filter((l) => l.status !== "en_stock");
  const totalKg = active.reduce((s, l) => s + l.quantity_kg, 0);
  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight flex items-center gap-2"><Warehouse className="w-5 h-5 text-emerald-800" aria-hidden /> Mes stocks</h1>
            <p className="text-sm text-neutral-600 mt-1">Suivez vos récoltes stockées pour éviter les pertes, et choisissez le bon moment pour vendre.</p>
          </div>
          <Button onClick={() => setAdding(!adding)} variant={adding ? "outline" : "primary"}><Plus className="w-4 h-4" aria-hidden /> {adding ? "Fermer" : "Déclarer un stock"}</Button>
        </div>
        {!!active.length && <p className="text-sm mt-3 pt-3 border-t border-neutral-100">En stock : <strong className="tabular-nums">{formatNumber(totalKg)} kg</strong> en {active.length} lot{active.length > 1 ? "s" : ""}</p>}
      </Card>
      {adding && <Card><CardHeader icon={Plus} title="Nouveau stock" /><NewLotForm onDone={() => setAdding(false)} /></Card>}
      <Card>
        <CardHeader icon={Warehouse} title="En cours" />
        {q.isLoading && <Loading />}
        {q.isSuccess && !active.length && <Empty>Aucun stock en cours.</Empty>}
        <ul className="space-y-3">{active.map((l) => <LotCard key={l.id} lot={l} />)}</ul>
      </Card>
      {!!closed.length && (
        <Card>
          <CardHeader title="Stocks clos" />
          <ul className="space-y-3">{closed.map((l) => <LotCard key={l.id} lot={l} />)}</ul>
        </Card>
      )}
    </div>
  );
}
