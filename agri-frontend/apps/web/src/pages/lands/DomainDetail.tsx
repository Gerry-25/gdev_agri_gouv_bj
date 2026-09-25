import { api, apiErrorMessage, formatDate, formatNumber, useSession } from "@agri/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CheckCircle2, ClipboardList, Compass, Database, FileSignature, Sparkles, XCircle } from "lucide-react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { MapView } from "../../components/MapView";
import { Alert, Badge, Button, Card, CardHeader, Loading } from "../../components/ui";
import { featureBounds } from "../../lib/geometry";
import { compressImage } from "../../lib/image";
import { unwrap } from "../../lib/queries";
import { PlanView } from "./PlanView";
import type { Domain, Environment, PlanDoc, Readiness } from "./types";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";
const Field = ({ id, label, children, className = "" }: { id: string; label: string; children: ReactNode; className?: string }) => (
  <div className={className}><label htmlFor={id} className="block text-sm font-semibold mb-1">{label}</label>{children}</div>
);
function Select({ id, value, onChange, options }: { id: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={inputCls}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>;
}
function Multi({ legend, value, onChange, options }: { legend: string; value: string[]; onChange: (v: string[]) => void; options: [string, string][] }) {
  return (
    <fieldset className="sm:col-span-2">
      <legend className="text-sm font-semibold mb-1">{legend}</legend>
      <div className="flex flex-wrap gap-2">{options.map(([v, l]) => {
        const on = value.includes(v);
        return <button key={v} type="button" aria-pressed={on} onClick={() => onChange(on ? value.filter((x) => x !== v) : [...value, v])}
                       className={`min-h-9 px-3 rounded-full border text-sm cursor-pointer ${on ? "bg-emerald-800 border-emerald-800 text-white" : "bg-white border-neutral-300 text-neutral-700"}`}>{l}</button>;
      })}</div>
    </fieldset>
  );
}
const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

// --- Profil environnemental --------------------------------------------------------------

const STATUS_LABEL = { ok: ["Disponible", "green"], indisponible: ["Service indisponible", "amber"], non_configure: ["Non configuré", "neutral"], absent: ["Non collecté", "neutral"] } as const;

function EnvironmentCard({ domain }: { domain: Domain & { environment?: Environment } }) {
  const qc = useQueryClient();
  const refresh = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/domains/{domain_id}/environment", { params: { path: { domain_id: domain.id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["domain", domain.id] }),
  });
  const env = domain.environment;
  const c = env?.climate?.data, r = env?.relief?.data, a = env?.access?.data;
  const src = (k: "soil" | "climate" | "relief" | "access", label: string) => {
    const [l, tone] = STATUS_LABEL[(env?.[k]?.status ?? "absent") as keyof typeof STATUS_LABEL];
    return <li className="flex justify-between gap-2"><span>{label}</span><Badge tone={tone}>{l}</Badge></li>;
  };
  return (
    <Card>
      <CardHeader icon={Database} title="Profil environnemental (automatique)" action={<Button variant="outline" className="min-h-9" onClick={() => refresh.mutate()} loading={refresh.isPending}>{env ? "Actualiser" : "Collecter"}</Button>} />
      {!env ? <p className="text-sm text-neutral-600">Sol, climat sur 10 ans, relief et accessibilité seront collectés à partir du contour.</p> : (
        <div className="grid gap-4 md:grid-cols-2 text-sm">
          <ul className="space-y-1.5">{src("soil", "Sol (iSDAsoil)")}{src("climate", "Climat (10 ans)")}{src("relief", "Relief")}{src("access", "Accessibilité")}</ul>
          <div className="space-y-1.5">
            {c && <p><strong>Pluie : </strong>{formatNumber(c.annual_rainfall_mm?.mean ?? 0)} mm/an en moyenne ({formatNumber(c.annual_rainfall_mm?.min ?? 0)} à {formatNumber(c.annual_rainfall_mm?.max ?? 0)}) · saisons : {c.rainy_seasons?.join(", ")}</p>}
            {r && <p><strong>Relief : </strong>pente {r.slope_class} ({formatNumber(r.max_slope_pct ?? 0, 1)} %), {r.landscape_position}</p>}
            {a && <p><strong>Accès : </strong>route à {a.route ? `${formatNumber(a.route.distance_km, 1)} km` : "?"}, cours d'eau à {a.cours_eau ? `${formatNumber(a.cours_eau.distance_km, 1)} km` : "?"}, marché à {a.marche ? `${formatNumber(a.marche.distance_km, 1)} km` : "?"}</p>}
            {env.zone && <p><strong>Zone agroécologique : </strong>{env.zone.candidates.map((z) => `${z.zone}. ${z.name}`).join(" ou ")} <span className="text-neutral-500">({env.zone.basis})</span></p>}
          </div>
          {!!env.soil_reading?.length && (
            <ul className="md:col-span-2 grid gap-2 sm:grid-cols-3">{env.soil_reading.map((s) => (
              <li key={s.parameter} className="p-2 rounded border border-neutral-200 bg-neutral-50"><span className="font-semibold">{s.parameter}</span> : {s.level}{s.uncertainty === "forte" ? " (incertain)" : ""}<span className="block text-neutral-600">{s.comment}</span></li>
            ))}</ul>
          )}
          {env.fetched_at && <p className="md:col-span-2 text-xs text-neutral-500">Collecté le {formatDate(env.fetched_at)}</p>}
        </div>
      )}
      {refresh.isError && <Alert tone="error">{(refresh.error as Error).message}</Alert>}
    </Card>
  );
}

// --- Relevé de terrain et orientations -------------------------------------------------------

type Survey = Record<string, unknown>;

function SurveyForm({ domain }: { domain: Domain & { survey?: Survey } }) {
  const qc = useQueryClient();
  const s = domain.survey ?? {};
  const [f, setF] = useState({
    survey_date: String(s.survey_date ?? new Date().toISOString().slice(0, 10)), agroecological_zone: String(s.agroecological_zone ?? ""),
    land_use_history: String(s.land_use_history ?? "jachere"), fallow_years: String(s.fallow_years ?? ""), last_crops: ((s.last_crops as string[]) ?? []).join(", "),
    water_sources: (s.water_sources as string[]) ?? [], irrigation_possible: String(s.irrigation_possible ?? ""), flooding_observed: String(s.flooding_observed ?? "inconnu"),
    vegetation_cover: String(s.vegetation_cover ?? "arbustive"), trees_to_preserve: String(s.trees_to_preserve ?? ""), erosion: String(s.erosion ?? "aucune"),
    stoniness: String(s.stoniness ?? "faible"), clearing_needed: String(s.clearing_needed ?? "leger"), rainy_season_access: String(s.rainy_season_access ?? "bonne"),
    infrastructures: (s.infrastructures as string[]) ?? [], labor_availability: String(s.labor_availability ?? "moyenne"), customary_uses: String(s.customary_uses ?? ""), observations: String(s.observations ?? ""),
  });
  const set = (k: keyof typeof f) => (v: string | string[]) => setF({ ...f, [k]: v });
  const save = useMutation({
    mutationFn: async () => unwrap(await api.PUT("/api/v1/domains/{domain_id}/survey", { params: { path: { domain_id: domain.id } }, body: {
      ...f, agroecological_zone: f.agroecological_zone ? Number(f.agroecological_zone) : undefined, fallow_years: f.fallow_years ? Number(f.fallow_years) : undefined,
      last_crops: split(f.last_crops), irrigation_possible: f.irrigation_possible === "" ? undefined : f.irrigation_possible === "true",
      trees_to_preserve: f.trees_to_preserve || undefined, customary_uses: f.customary_uses || undefined, observations: f.observations || undefined,
    } as never })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["domain", domain.id] }),
  });
  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="grid gap-3 sm:grid-cols-2">
      <Field id="sv-date" label="Date de la visite"><input id="sv-date" type="date" value={f.survey_date} onChange={(e) => set("survey_date")(e.target.value)} className={inputCls} /></Field>
      <Field id="sv-zone" label="Zone agroécologique confirmée"><Select id="sv-zone" value={f.agroecological_zone} onChange={set("agroecological_zone")} options={[["", "Non confirmée"], ...[1, 2, 3, 4, 5, 6, 7, 8].map((z) => [String(z), `Zone ${z}`] as [string, string])]} /></Field>
      <Field id="sv-use" label="Usage antérieur"><Select id="sv-use" value={f.land_use_history} onChange={set("land_use_history")} options={[["jachere", "Jachère"], ["culture", "Cultivée"], ["foret_savane", "Forêt ou savane"], ["paturage", "Pâturage"], ["inconnu", "Inconnu"]]} /></Field>
      <Field id="sv-fallow" label="Années de jachère"><input id="sv-fallow" inputMode="numeric" value={f.fallow_years} onChange={(e) => set("fallow_years")(e.target.value.replace(/\D/g, ""))} className={inputCls} /></Field>
      <Field id="sv-last" label="Dernières cultures (séparées par des virgules)" className="sm:col-span-2"><input id="sv-last" value={f.last_crops} onChange={(e) => set("last_crops")(e.target.value)} className={inputCls} /></Field>
      <Multi legend="Sources d'eau" value={f.water_sources} onChange={set("water_sources")} options={[["forage", "Forage"], ["puits", "Puits"], ["riviere", "Rivière"], ["bas_fond", "Bas-fond"], ["retenue_eau", "Retenue d'eau"], ["aucune", "Aucune"]]} />
      <Field id="sv-irr" label="Irrigation possible"><Select id="sv-irr" value={f.irrigation_possible} onChange={set("irrigation_possible")} options={[["", "Ne sait pas"], ["true", "Oui"], ["false", "Non"]]} /></Field>
      <Field id="sv-flood" label="Inondations constatées"><Select id="sv-flood" value={f.flooding_observed} onChange={set("flooding_observed")} options={[["jamais", "Jamais"], ["occasionnel", "Occasionnelles"], ["frequent", "Fréquentes"], ["inconnu", "Inconnu"]]} /></Field>
      <Field id="sv-veg" label="Couvert végétal"><Select id="sv-veg" value={f.vegetation_cover} onChange={set("vegetation_cover")} options={[["sol_nu", "Sol nu"], ["herbacee", "Herbacé"], ["arbustive", "Arbustif"], ["arboree", "Arboré"], ["dense", "Dense"]]} /></Field>
      <Field id="sv-trees" label="Arbres à conserver"><input id="sv-trees" value={f.trees_to_preserve} onChange={(e) => set("trees_to_preserve")(e.target.value)} className={inputCls} placeholder="Karité, néré…" /></Field>
      <Field id="sv-ero" label="Érosion"><Select id="sv-ero" value={f.erosion} onChange={set("erosion")} options={[["aucune", "Aucune"], ["legere", "Légère"], ["forte", "Forte"]]} /></Field>
      <Field id="sv-stone" label="Pierrosité"><Select id="sv-stone" value={f.stoniness} onChange={set("stoniness")} options={[["faible", "Faible"], ["moyenne", "Moyenne"], ["forte", "Forte"]]} /></Field>
      <Field id="sv-clear" label="Défrichement nécessaire"><Select id="sv-clear" value={f.clearing_needed} onChange={set("clearing_needed")} options={[["aucun", "Aucun"], ["leger", "Léger"], ["important", "Important"]]} /></Field>
      <Field id="sv-acc" label="Accès en saison des pluies"><Select id="sv-acc" value={f.rainy_season_access} onChange={set("rainy_season_access")} options={[["bonne", "Bon"], ["difficile", "Difficile"], ["impossible", "Impossible"]]} /></Field>
      <Multi legend="Infrastructures présentes" value={f.infrastructures} onChange={set("infrastructures")} options={[["cloture", "Clôture"], ["magasin", "Magasin"], ["electricite", "Électricité"], ["logement", "Logement"], ["forage_equipe", "Forage équipé"], ["piste_interne", "Piste interne"]]} />
      <Field id="sv-lab" label="Main-d'œuvre disponible"><Select id="sv-lab" value={f.labor_availability} onChange={set("labor_availability")} options={[["faible", "Faible"], ["moyenne", "Moyenne"], ["bonne", "Bonne"]]} /></Field>
      <Field id="sv-cust" label="Usages coutumiers ou occupants à respecter" className="sm:col-span-2"><input id="sv-cust" value={f.customary_uses} onChange={(e) => set("customary_uses")(e.target.value)} className={inputCls} /></Field>
      <Field id="sv-obs" label="Observations" className="sm:col-span-2"><textarea id="sv-obs" rows={3} value={f.observations} onChange={(e) => set("observations")(e.target.value)} className={inputCls} /></Field>
      {save.isError && <div className="sm:col-span-2"><Alert tone="error">{(save.error as Error).message}</Alert></div>}
      {save.isSuccess && <div className="sm:col-span-2"><Alert tone="success">Relevé enregistré.</Alert></div>}
      <Button type="submit" className="sm:col-span-2" loading={save.isPending}>Enregistrer le relevé</Button>
    </form>
  );
}

function OrientationForm({ domain }: { domain: Domain & { orientation?: Survey } }) {
  const qc = useQueryClient();
  const o = domain.orientation ?? {};
  const [f, setF] = useState({
    vocation: String(o.vocation ?? "mixte"), priority_crops: ((o.priority_crops as string[]) ?? []).join(", "), excluded_crops: ((o.excluded_crops as string[]) ?? []).join(", "),
    investment_level: String(o.investment_level ?? "moyen"), mechanization: String(o.mechanization ?? "attelee"), min_valorization_pct: String(o.min_valorization_pct ?? 80), notes: String(o.notes ?? ""),
  });
  const save = useMutation({
    mutationFn: async () => unwrap(await api.PUT("/api/v1/domains/{domain_id}/orientation", { params: { path: { domain_id: domain.id } }, body: {
      ...f, priority_crops: split(f.priority_crops), excluded_crops: split(f.excluded_crops), min_valorization_pct: Number(f.min_valorization_pct), notes: f.notes || undefined,
    } as never })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["domain", domain.id] }),
  });
  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="grid gap-3 sm:grid-cols-2">
      <Field id="or-voc" label="Vocation"><Select id="or-voc" value={f.vocation} onChange={(v) => setF({ ...f, vocation: v })} options={[["vivrier", "Vivrier"], ["rente_export", "Rente et export"], ["semences", "Production de semences"], ["jeunes_entrepreneurs", "Jeunes entrepreneurs"], ["mixte", "Mixte"]]} /></Field>
      <Field id="or-min" label="Part minimale à mettre en valeur (%)"><input id="or-min" inputMode="numeric" value={f.min_valorization_pct} onChange={(e) => setF({ ...f, min_valorization_pct: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
      <Field id="or-pri" label="Cultures prioritaires"><input id="or-pri" value={f.priority_crops} onChange={(e) => setF({ ...f, priority_crops: e.target.value })} className={inputCls} placeholder="Soja, Maïs" /></Field>
      <Field id="or-exc" label="Cultures exclues"><input id="or-exc" value={f.excluded_crops} onChange={(e) => setF({ ...f, excluded_crops: e.target.value })} className={inputCls} /></Field>
      <Field id="or-inv" label="Niveau d'investissement attendu"><Select id="or-inv" value={f.investment_level} onChange={(v) => setF({ ...f, investment_level: v })} options={[["faible", "Faible"], ["moyen", "Moyen"], ["eleve", "Élevé"]]} /></Field>
      <Field id="or-mec" label="Mécanisation"><Select id="or-mec" value={f.mechanization} onChange={(v) => setF({ ...f, mechanization: v })} options={[["manuelle", "Manuelle"], ["attelee", "Traction animale"], ["motorisee", "Motorisée"]]} /></Field>
      <Field id="or-notes" label="Notes" className="sm:col-span-2"><textarea id="or-notes" rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} className={inputCls} /></Field>
      {save.isSuccess && <div className="sm:col-span-2"><Alert tone="success">Orientations enregistrées.</Alert></div>}
      {save.isError && <div className="sm:col-span-2"><Alert tone="error">{(save.error as Error).message}</Alert></div>}
      <Button type="submit" className="sm:col-span-2" loading={save.isPending}>Enregistrer les orientations</Button>
    </form>
  );
}

function Photos({ domain }: { domain: Domain }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["domain", domain.id, "photos"], queryFn: async () => unwrap(await api.GET("/api/v1/domains/{domain_id}/photos", { params: { path: { domain_id: domain.id } } })) as unknown as { id: string; caption?: string }[] });
  const [err, setErr] = useState<string | null>(null);
  const add = async (file?: File) => {
    if (!file) return;
    setErr(null);
    const form = new FormData();
    form.append("file", await compressImage(file, 1280), "photo.jpg");
    await new Promise<void>((resolve) => navigator.geolocation?.getCurrentPosition(
      (p) => { form.append("latitude", String(p.coords.latitude)); form.append("longitude", String(p.coords.longitude)); resolve(); }, () => resolve(), { timeout: 5000 }) ?? resolve());
    const { error } = await api.POST("/api/v1/domains/{domain_id}/photos", { params: { path: { domain_id: domain.id } }, body: form as never });
    if (error) setErr(apiErrorMessage(error));
    qc.invalidateQueries({ queryKey: ["domain", domain.id] });
  };
  return (
    <div className="space-y-3">
      <p className="text-sm text-neutral-600">{q.data?.length ?? 0} photo(s). Au moins 4 recommandées : vue d'ensemble, sol, végétation, point d'eau. Les 4 premières sont transmises à l'IA.</p>
      <label className="inline-flex min-h-11 px-4 rounded border border-neutral-300 text-sm font-semibold items-center gap-2 cursor-pointer hover:bg-neutral-50 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-emerald-700">
        <Camera className="w-4 h-4" aria-hidden /> Ajouter une photo
        <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => add(e.target.files?.[0])} />
      </label>
      {err && <Alert tone="error">{err}</Alert>}
    </div>
  );
}

// --- Plans ---------------------------------------------------------------------------------

function Plans({ domain, ready }: { domain: Domain; ready: boolean }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { user } = useSession();
  const plans = useQuery({ queryKey: ["domain", domain.id, "plans"], queryFn: async () => unwrap(await api.GET("/api/v1/domains/{domain_id}/plans", { params: { path: { domain_id: domain.id } } })) as PlanDoc[] });
  const generate = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/domains/{domain_id}/plans", { params: { path: { domain_id: domain.id } } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["domain", domain.id] }); },
  });
  const [review, setReview] = useState({ expert_name: "", organization: "INRAB", note: "", status: "valide" });
  const doReview = useMutation({
    mutationFn: async (id: string) => unwrap(await api.PATCH("/api/v1/domains/plans/{plan_id}/review", { params: { path: { plan_id: id } }, body: review as never })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["domain", domain.id] }),
  });
  const latest = plans.data?.[0];
  return (
    <Card>
      <CardHeader icon={Sparkles} title="Plan de mise en valeur (IA)" action={
        <Button className="min-h-9" onClick={() => generate.mutate()} loading={generate.isPending} disabled={!ready}>{latest ? "Nouvelle version" : "Générer le plan"}</Button>} />
      {!ready && <Alert tone="info">Complétez les éléments obligatoires de la liste de contrôle pour générer un plan.</Alert>}
      {generate.isPending && <p className="text-sm text-neutral-600">Analyse du sol, du climat, du terrain et des photos… cela peut prendre une minute.</p>}
      {generate.isError && <Alert tone="error">{(generate.error as Error).message}</Alert>}
      {plans.isLoading && <Loading />}
      {latest && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold">Version {latest.version}</span> · {formatDate(latest.created_at)} ·
            <Badge tone={latest.status === "valide" ? "green" : latest.status === "a_revoir" ? "red" : "amber"}>{latest.status === "valide" ? "Validé par un expert" : latest.status === "a_revoir" ? "À revoir" : "Proposition, non relue"}</Badge>
          </div>
          <PlanView plan={latest.plan} />
          {latest.review && <p className="text-sm text-neutral-700">Relecture : {String((latest.review as Record<string, unknown>).expert_name)} ({String((latest.review as Record<string, unknown>).organization)}) · {String((latest.review as Record<string, unknown>).note)}</p>}
          {latest.status === "proposition" && (
            latest.created_by === user?.npi ? (
              <Alert tone="info">La relecture doit être enregistrée par un autre agent que celui qui a généré le plan.</Alert>
            ) : (
              <form onSubmit={(e) => { e.preventDefault(); doReview.mutate(latest.id); }} className="grid gap-3 sm:grid-cols-2 p-3 rounded-lg border border-neutral-200 bg-neutral-50">
                <h3 className="sm:col-span-2 text-sm font-bold flex items-center gap-2"><FileSignature className="w-4 h-4" aria-hidden /> Relecture par un expert</h3>
                <Field id="rv-name" label="Nom de l'expert"><input id="rv-name" value={review.expert_name} onChange={(e) => setReview({ ...review, expert_name: e.target.value })} className={inputCls} /></Field>
                <Field id="rv-org" label="Organisme"><input id="rv-org" value={review.organization} onChange={(e) => setReview({ ...review, organization: e.target.value })} className={inputCls} /></Field>
                <Field id="rv-note" label="Avis" className="sm:col-span-2"><textarea id="rv-note" rows={2} value={review.note} onChange={(e) => setReview({ ...review, note: e.target.value })} className={inputCls} /></Field>
                <div className="sm:col-span-2 flex flex-wrap gap-2">
                  <Button type="submit" onClick={() => setReview((r) => ({ ...r, status: "valide" }))} disabled={review.expert_name.length < 3 || review.note.length < 5}>Valider le plan</Button>
                  <Button type="submit" variant="danger" onClick={() => setReview((r) => ({ ...r, status: "a_revoir" }))} disabled={review.expert_name.length < 3 || review.note.length < 5}>Demander une révision</Button>
                </div>
                {doReview.isError && <div className="sm:col-span-2"><Alert tone="error">{(doReview.error as Error).message}</Alert></div>}
              </form>
            )
          )}
          {domain.status === "disponible" && (
            <Button variant={latest.status === "valide" ? "primary" : "outline"} onClick={() => navigate(`/concessions/terres/${domain.id}/appel?plan=${latest.id}`)}>
              Préparer l'appel à candidatures à partir de ce plan
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}

export function DomainDetail() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["domain", id], queryFn: async () => unwrap(await api.GET("/api/v1/domains/{domain_id}", { params: { path: { domain_id: id! } } })) as unknown as Domain & { environment?: Environment; survey?: Survey; orientation?: Survey } });
  const ready = useQuery({ queryKey: ["domain", id, "readiness", q.dataUpdatedAt], enabled: !!q.data, queryFn: async () => unwrap(await api.GET("/api/v1/domains/{domain_id}/readiness", { params: { path: { domain_id: id! } } })) as unknown as Readiness });
  const [panel, setPanel] = useState<"survey" | "orientation" | "photos" | null>(null);
  const fc = useMemo<GeoJSON.FeatureCollection | undefined>(() => q.data && ({ type: "FeatureCollection", features: [{ type: "Feature", properties: { id: q.data.id, verification_status: "verifiee" }, geometry: q.data.boundary as unknown as GeoJSON.Geometry }] }), [q.data]);
  if (q.isLoading) return <Loading />;
  if (!q.data) return <Alert tone="error">Terre introuvable.</Alert>;
  const d = q.data;
  return (
    <div className="space-y-5">
      <Card>
        <p className="text-xs font-bold text-emerald-800">Terre du domaine privé de l'État{d.land_title_ref ? ` · ${d.land_title_ref}` : ""}</p>
        <h1 className="text-xl font-bold">{d.name}</h1>
        <p className="text-sm text-neutral-600">{d.commune} ({d.department}) · {formatNumber(d.surface_hectares, 1)} ha · statut : {d.status.replace("_", " ")}</p>
        {d.dispute_flag && <div className="mt-3"><Alert tone="error">Litige ouvert sur cette terre : aucun appel ne peut être publié avant sa clôture.</Alert></div>}
      </Card>
      <MapView className="h-72" parcels={fc} fitBounds={featureBounds(fc)} label="Contour de la terre" />
      <Card>
        <CardHeader icon={ClipboardList} title={`Préparation du plan (${ready.data?.completeness_pct ?? 0} %)`} />
        <ul className="space-y-1.5 text-sm">
          {ready.data?.checks.map((c) => (
            <li key={c.item} className="flex items-center gap-2">
              {c.ok ? <CheckCircle2 className="w-4 h-4 text-emerald-700 shrink-0" aria-hidden /> : <XCircle className={`w-4 h-4 shrink-0 ${c.required ? "text-red-600" : "text-neutral-400"}`} aria-hidden />}
              <span>{c.item}{c.required ? "" : " (recommandé)"}</span>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2 mt-4">
          <Button variant="outline" onClick={() => setPanel(panel === "survey" ? null : "survey")}><Compass className="w-4 h-4" aria-hidden /> Relevé de terrain</Button>
          <Button variant="outline" onClick={() => setPanel(panel === "orientation" ? null : "orientation")}>Orientations de l'État</Button>
          <Button variant="outline" onClick={() => setPanel(panel === "photos" ? null : "photos")}><Camera className="w-4 h-4" aria-hidden /> Photos</Button>
        </div>
        {panel && <div className="mt-4 pt-4 border-t border-neutral-100">{panel === "survey" ? <SurveyForm domain={d} /> : panel === "orientation" ? <OrientationForm domain={d} /> : <Photos domain={d} />}</div>}
      </Card>
      <EnvironmentCard domain={d} />
      <Plans domain={d} ready={!!ready.data?.ready} />
    </div>
  );
}
