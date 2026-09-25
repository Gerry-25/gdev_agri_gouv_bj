import { api, apiErrorMessage } from "@agri/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Alert, Button, Card, CardHeader, Loading } from "../../components/ui";
import { unwrap } from "../../lib/queries";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";
const today = () => new Date().toISOString().slice(0, 10);
const plusDays = (n: number) => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10);

/** Rédaction d'un appel à candidatures, préremplie depuis le plan de mise en valeur. */
export function NewCallPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const planId = params.get("plan");
  const navigate = useNavigate();
  const draft = useQuery({
    queryKey: ["plan", planId, "draft"], enabled: !!planId,
    queryFn: async () => unwrap(await api.GET("/api/v1/domains/plans/{plan_id}/call-draft", { params: { path: { plan_id: planId! } } })) as unknown as
      { title: string; description: string; cahier_des_charges: string; allowed_crops: string[]; mise_en_valeur_months: number; warning: string | null },
  });
  const [f, setF] = useState({ title: "", description: "", cahier_des_charges: "", allowed_crops: "", contract_type: "concession", duration_years: "5",
    annual_fee_fcfa_per_ha: "15000", mise_en_valeur_months: "12", min_score: "50", opens_at: today(), closes_at: plusDays(21) });
  useEffect(() => {
    const d = draft.data;
    if (d) setF((x) => ({ ...x, title: d.title, description: d.description, cahier_des_charges: d.cahier_des_charges, allowed_crops: d.allowed_crops.join(", "), mise_en_valeur_months: String(d.mise_en_valeur_months) }));
  }, [draft.data]);
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const { error: err } = await api.POST("/api/v1/domains/{domain_id}/calls", { params: { path: { domain_id: id! } }, body: {
      title: f.title, description: f.description, cahier_des_charges: f.cahier_des_charges, allowed_crops: f.allowed_crops.split(",").map((c) => c.trim()).filter(Boolean),
      contract_type: f.contract_type as never, duration_years: Number(f.duration_years), annual_fee_fcfa_per_ha: Number(f.annual_fee_fcfa_per_ha),
      mise_en_valeur_months: Number(f.mise_en_valeur_months), min_score: Number(f.min_score), plan_id: planId ?? undefined,
      opens_at: new Date(f.opens_at).toISOString(), closes_at: new Date(`${f.closes_at}T23:59:00`).toISOString(),
    } });
    if (err) return setError(apiErrorMessage(err));
    navigate("/concessions?onglet=appels");
  };
  const L = ({ id: i, label }: { id: string; label: string }) => <label htmlFor={i} className="block text-sm font-semibold mb-1">{label}</label>;
  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <Card>
        <CardHeader title="Nouvel appel à candidatures (brouillon)" />
        {draft.isLoading && <Loading label="Préremplissage depuis le plan…" />}
        {draft.data?.warning && <div className="mb-3"><Alert tone="warning">{draft.data.warning}</Alert></div>}
        <p className="text-sm text-neutral-600 mb-4">L'appel sera publié par un superviseur, autre que vous, après relecture. La durée de publicité minimale s'applique à partir de la publication.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2"><L id="ct" label="Titre" /><input id="ct" value={f.title} onChange={set("title")} className={inputCls} /></div>
          <div className="sm:col-span-2"><L id="cd" label="Description" /><textarea id="cd" rows={3} value={f.description} onChange={set("description")} className={inputCls} /></div>
          <div className="sm:col-span-2"><L id="cc" label="Cahier des charges" /><textarea id="cc" rows={10} value={f.cahier_des_charges} onChange={set("cahier_des_charges")} className={`${inputCls} font-mono text-sm`} /></div>
          <div className="sm:col-span-2"><L id="ca" label="Cultures autorisées" /><input id="ca" value={f.allowed_crops} onChange={set("allowed_crops")} className={inputCls} /></div>
          <div><L id="ck" label="Type de contrat" /><select id="ck" value={f.contract_type} onChange={set("contract_type")} className={inputCls}><option value="concession">Concession</option><option value="bail_ordinaire">Bail ordinaire</option><option value="bail_emphyteotique">Bail emphytéotique</option></select></div>
          <div><L id="cy" label="Durée (années)" /><input id="cy" inputMode="numeric" value={f.duration_years} onChange={set("duration_years")} className={inputCls} /></div>
          <div><L id="cf" label="Redevance annuelle (FCFA/ha)" /><input id="cf" inputMode="numeric" value={f.annual_fee_fcfa_per_ha} onChange={set("annual_fee_fcfa_per_ha")} className={inputCls} /></div>
          <div><L id="cm" label="Délai de mise en valeur (mois)" /><input id="cm" inputMode="numeric" value={f.mise_en_valeur_months} onChange={set("mise_en_valeur_months")} className={inputCls} /></div>
          <div><L id="cs" label="Score minimal (sur 100)" /><input id="cs" inputMode="numeric" value={f.min_score} onChange={set("min_score")} className={inputCls} /></div>
          <div><L id="co" label="Ouverture" /><input id="co" type="date" value={f.opens_at} onChange={set("opens_at")} className={inputCls} /></div>
          <div><L id="cl" label="Clôture" /><input id="cl" type="date" value={f.closes_at} onChange={set("closes_at")} className={inputCls} /></div>
        </div>
      </Card>
      {error && <Alert tone="error">{error}</Alert>}
      <Button type="submit" className="w-full min-h-12" disabled={f.title.length < 5 || f.cahier_des_charges.length < 20 || !f.allowed_crops}>Enregistrer le brouillon</Button>
    </form>
  );
}
