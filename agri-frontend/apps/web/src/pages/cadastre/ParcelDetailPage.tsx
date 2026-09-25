import { api, apiErrorMessage, formatDate, formatNumber, useSession } from "@agri/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight, ClipboardCheck, FlaskConical, MapPin, Pencil, Scale, Sparkles, Sprout, Trash2, Wheat,
} from "lucide-react";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AudioButton } from "../../components/AudioButton";
import { MapView } from "../../components/MapView";
import { Alert, Badge, Button, buttonClass, Card, CardHeader, Empty, Loading } from "../../components/ui";
import { WeatherWidget } from "../../components/WeatherWidget";
import { featureBounds } from "../../lib/geometry";
import { type Land, unwrap } from "../../lib/queries";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";

function Field({ label, children, id }: { label: string; children: ReactNode; id: string }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-semibold mb-1">{label}</label>
      {children}
    </div>
  );
}

function StatusBadge({ land }: { land: Land }) {
  if (land.dispute_flag) return <Badge tone="red">Litige en cours</Badge>;
  if (land.verification_status === "verifiee") return <Badge tone="green">Vérifiée par un agent</Badge>;
  if (land.verification_status === "rejetee") return <Badge tone="red">Non validée</Badge>;
  return <Badge tone="amber">En attente de vérification</Badge>;
}

const CAPTURE = { gps_walk: "Relevé GPS en marchant", map_drawing: "Tracé sur la carte", survey: "Relevé de géomètre" } as Record<string, string>;

// --- Récoltes -------------------------------------------------------------------------

function Harvests({ land, owner }: { land: Land; owner: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["harvests", land.id], queryFn: async () => unwrap(await api.GET("/api/v1/lands/{land_id}/harvests", { params: { path: { land_id: land.id } } })) });
  const year = new Date().getFullYear();
  const [form, setForm] = useState({ season: `${year}-A`, actual_yield_kg: "", harvest_date: "" });
  const add = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/lands/{land_id}/harvests", {
      params: { path: { land_id: land.id } },
      body: { season: form.season, actual_yield_kg: Number(form.actual_yield_kg), harvest_date: form.harvest_date || undefined },
    })),
    onSuccess: () => {
      setForm((f) => ({ ...f, actual_yield_kg: "" }));
      qc.invalidateQueries({ queryKey: ["harvests", land.id] });
      qc.invalidateQueries({ queryKey: ["performance"] });
    },
  });
  return (
    <Card>
      <CardHeader icon={Wheat} title="Récoltes" />
      {q.isLoading && <Loading />}
      {q.data?.length === 0 && <p className="text-sm text-neutral-600 mb-3">Aucune récolte déclarée. Les récoltes comptent pour votre score une fois la parcelle vérifiée.</p>}
      {!!q.data?.length && (
        <div className="overflow-x-auto mb-4">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-neutral-500 border-b border-neutral-200"><th className="py-2 pr-3 font-semibold">Saison</th><th className="py-2 pr-3 font-semibold">Culture</th><th className="py-2 pr-3 font-semibold text-right">Récolte</th><th className="py-2 font-semibold text-right">Rendement</th></tr></thead>
            <tbody>
              {q.data.map((h) => (
                <tr key={h.id} className="border-b border-neutral-100">
                  <td className="py-2 pr-3 tabular-nums">{h.season}</td>
                  <td className="py-2 pr-3">{h.crop_type}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{formatNumber(h.actual_yield_kg)} kg</td>
                  <td className="py-2 text-right tabular-nums">{h.yield_kg_per_ha ? `${formatNumber(h.yield_kg_per_ha)} kg/ha` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {owner && (
        <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="grid gap-3 sm:grid-cols-4 items-end">
          <Field id="season" label="Saison"><input id="season" value={form.season} onChange={(e) => setForm({ ...form, season: e.target.value.toUpperCase() })} className={inputCls} placeholder="2026-A" /></Field>
          <Field id="qty" label="Quantité récoltée (kg)"><input id="qty" inputMode="numeric" value={form.actual_yield_kg} onChange={(e) => setForm({ ...form, actual_yield_kg: e.target.value.replace(/\D/g, "") })} className={`${inputCls} tabular-nums`} /></Field>
          <Field id="hdate" label="Date (facultatif)"><input id="hdate" type="date" value={form.harvest_date} onChange={(e) => setForm({ ...form, harvest_date: e.target.value })} className={inputCls} /></Field>
          <Button type="submit" loading={add.isPending} disabled={!form.actual_yield_kg}>Déclarer</Button>
          {add.isError && <div className="sm:col-span-4"><Alert tone="error">{(add.error as Error).message}</Alert></div>}
        </form>
      )}
    </Card>
  );
}

// --- Sol et plan de fumure (IA) -----------------------------------------------------------

interface SoilReading { parameter: string; value: number; unit?: string | null; level: string; comment: string; uncertainty?: string | null }
interface Input { product: string; dose: string; timing: string; rationale: string }
interface FertPlan {
  simple_summary: string; soil_diagnosis: { parameter: string; level: string; comment: string }[];
  amendments: Input[]; organic_inputs: Input[]; mineral_inputs: Input[]; rotation_advice: string;
  expected_yield_kg_ha: { low: number; high: number }; cost_estimate_fcfa_ha: { low: number; high: number }; warnings: string[];
}
interface FertDoc { id: string; crop_type: string; plan: FertPlan; created_at: string; disclaimer: string }

const LEVEL_TONE: Record<string, "green" | "amber" | "red" | "neutral"> = { correct: "green", bon: "green", moyen: "amber", faible: "red", acide: "red", basique: "amber" };
const RESOURCES = [["fumier", "Fumier"], ["compost", "Compost"], ["residus_culture", "Résidus de culture"], ["cendre", "Cendre"], ["fientes", "Fientes"]] as const;

function InputsTable({ title, rows }: { title: string; rows: Input[] }) {
  if (!rows.length) return null;
  return (
    <div>
      <h3 className="text-sm font-bold mb-1">{title}</h3>
      <ul className="space-y-1.5">
        {rows.map((r) => (
          <li key={r.product + r.timing} className="p-2.5 rounded border border-neutral-200 bg-white text-sm">
            <span className="font-semibold">{r.product}</span> · <span className="tabular-nums">{r.dose}</span> · {r.timing}
            <span className="block text-neutral-600">{r.rationale}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SoilAndFertilization({ land, owner }: { land: Land; owner: boolean }) {
  const qc = useQueryClient();
  const soil = useQuery({
    queryKey: ["soil", land.id],
    retry: 0,
    queryFn: async () => unwrap(await api.GET("/api/v1/lands/{land_id}/soil", { params: { path: { land_id: land.id } } })) as unknown as { reading: SoilReading[]; environment: { soil?: { status: string; source?: string } } },
  });
  const plans = useQuery({
    queryKey: ["fertilization", land.id],
    queryFn: async () => unwrap(await api.GET("/api/v1/lands/{land_id}/fertilization-plans", { params: { path: { land_id: land.id } } })) as unknown as FertDoc[],
  });
  const [resources, setResources] = useState<string[]>([]);
  const [budget, setBudget] = useState<"faible" | "moyen" | "eleve">("moyen");
  const generate = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/lands/{land_id}/fertilization-plans", {
      params: { path: { land_id: land.id } }, body: { organic_resources: resources as never, budget_level: budget },
    })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fertilization", land.id] }),
  });
  const latest = plans.data?.[0];
  const status = soil.data?.environment?.soil?.status;

  return (
    <Card>
      <CardHeader icon={FlaskConical} title="Sol et plan de fumure" />
      {soil.isLoading && <Loading label="Lecture du sol…" />}
      {status && status !== "ok" && (
        <Alert tone="info">
          {status === "non_configure" ? "Les données de sol ne sont pas encore activées sur ce serveur." : "Données de sol momentanément indisponibles."} Le plan restera général.
        </Alert>
      )}
      {!!soil.data?.reading?.length && (
        <div className="mb-4">
          <p className="text-xs text-neutral-500 mb-2">Estimation satellite ({soil.data.environment.soil?.source}), à confirmer par une analyse si besoin.</p>
          <ul className="grid gap-2 sm:grid-cols-2">
            {soil.data.reading.map((r) => (
              <li key={r.parameter} className="p-2.5 rounded border border-neutral-200 bg-neutral-50 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{r.parameter}</span>
                  <Badge tone={LEVEL_TONE[r.level] ?? "neutral"}>{r.level}</Badge>
                </div>
                <span className="block text-neutral-600 mt-1">{r.comment}</span>
                {r.uncertainty === "forte" && <span className="block text-xs text-amber-800 mt-1">Estimation incertaine</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {owner && (
        <div className="p-3 rounded-lg border border-emerald-200 bg-emerald-50/50 space-y-3">
          <p className="text-sm font-semibold flex items-center gap-2"><Sparkles className="w-4 h-4 text-emerald-800" aria-hidden /> Plan de fumure adapté à votre sol ({land.crop_type})</p>
          <fieldset>
            <legend className="text-sm mb-1.5">Ce que vous avez sous la main :</legend>
            <div className="flex flex-wrap gap-2">
              {RESOURCES.map(([value, label]) => {
                const on = resources.includes(value);
                return (
                  <button key={value} type="button" aria-pressed={on} onClick={() => setResources(on ? resources.filter((r) => r !== value) : [...resources, value])}
                          className={`min-h-9 px-3 rounded-full border text-sm cursor-pointer ${on ? "bg-emerald-800 border-emerald-800 text-white" : "bg-white border-neutral-300 text-neutral-700"}`}>
                    {label}
                  </button>
                );
              })}
            </div>
          </fieldset>
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="budget" className="text-sm">Budget</label>
            <select id="budget" value={budget} onChange={(e) => setBudget(e.target.value as typeof budget)} className="min-h-9 px-2 border border-neutral-300 rounded bg-white text-sm">
              <option value="faible">Faible</option><option value="moyen">Moyen</option><option value="eleve">Élevé</option>
            </select>
            <Button onClick={() => generate.mutate()} loading={generate.isPending}>Obtenir mon plan</Button>
          </div>
          {generate.isError && <Alert tone="error">{(generate.error as Error).message}</Alert>}
        </div>
      )}

      {latest && (
        <div className="mt-4 space-y-3">
          <div className="p-3 rounded-lg bg-white border border-neutral-200">
            <div className="flex items-start justify-between gap-2">
              <p className="font-semibold">{latest.plan.simple_summary}</p>
              <AudioButton path={{ kind: "fertilization", landId: land.id }} />
            </div>
            <p className="text-sm text-neutral-600 mt-1">
              Rendement visé : <span className="tabular-nums">{formatNumber(latest.plan.expected_yield_kg_ha.low)} à {formatNumber(latest.plan.expected_yield_kg_ha.high)} kg/ha</span> ·
              Coût estimé : <span className="tabular-nums">{formatNumber(latest.plan.cost_estimate_fcfa_ha.low)} à {formatNumber(latest.plan.cost_estimate_fcfa_ha.high)} FCFA/ha</span>
            </p>
          </div>
          <InputsTable title="Amendements" rows={latest.plan.amendments} />
          <InputsTable title="Apports organiques" rows={latest.plan.organic_inputs} />
          <InputsTable title="Engrais" rows={latest.plan.mineral_inputs} />
          {latest.plan.rotation_advice && <p className="text-sm"><strong>Rotation : </strong>{latest.plan.rotation_advice}</p>}
          {latest.plan.warnings.map((w) => <Alert key={w} tone="warning">{w}</Alert>)}
          <p className="text-xs text-neutral-500">{latest.disclaimer} Généré le {formatDate(latest.created_at)}. Demandez conseil à votre conseiller agricole avant d'acheter des intrants.</p>
        </div>
      )}
    </Card>
  );
}

// --- Litiges, transferts, actions ------------------------------------------------------------

const DISPUTE_STATUS = { ouvert: ["Ouvert", "red"], en_mediation: ["En médiation", "amber"], resolu: ["Résolu", "green"], rejete: ["Rejeté", "neutral"] } as const;

function Disputes({ land }: { land: Land }) {
  const q = useQuery({ queryKey: ["disputes", land.id], queryFn: async () => unwrap(await api.GET("/api/v1/lands/{land_id}/disputes", { params: { path: { land_id: land.id } } })) });
  if (!q.data?.length) return null;
  return (
    <Card>
      <CardHeader icon={Scale} title="Litiges" />
      <ul className="space-y-2">
        {q.data.map((d) => {
          const [label, tone] = DISPUTE_STATUS[d.status];
          return (
            <li key={d.id} className="p-3 rounded border border-neutral-200 text-sm space-y-1">
              <div className="flex items-center justify-between gap-2"><span className="font-semibold">{d.type === "chevauchement_domaine_etat" ? "Chevauchement avec une terre de l'État" : d.type === "chevauchement" ? "Chevauchement avec une parcelle voisine" : "Litige signalé"}</span><Badge tone={tone}>{label}</Badge></div>
              <p className="text-neutral-700">{d.reason}</p>
              {d.resolution_note && <p className="text-neutral-600">Décision : {d.resolution_note}</p>}
              <p className="text-xs text-neutral-500">Ouvert le {formatDate(d.created_at)}</p>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function OwnerActions({ land }: { land: Land }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [panel, setPanel] = useState<"edit" | "transfer" | null>(null);
  const [edit, setEdit] = useState({ crop_type: land.crop_type, estimated_yield_kg: String(land.estimated_yield_kg), locality: land.locality ?? "" });
  const [transfer, setTransfer] = useState({ new_owner_npi: "", reason: "vente", note: "" });
  const [msg, setMsg] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const done = (text: string) => { setMsg({ tone: "success", text }); setPanel(null); qc.invalidateQueries({ queryKey: ["land", land.id] }); qc.invalidateQueries({ queryKey: ["lands"] }); };
  const fail = (e: unknown) => setMsg({ tone: "error", text: apiErrorMessage(e) });

  const save = async (e: FormEvent) => {
    e.preventDefault();
    const { error } = await api.PATCH("/api/v1/lands/{land_id}", { params: { path: { land_id: land.id } },
      body: { crop_type: edit.crop_type, estimated_yield_kg: Number(edit.estimated_yield_kg), locality: edit.locality || undefined } });
    error ? fail(error) : done("Informations enregistrées.");
  };
  const requestTransfer = async (e: FormEvent) => {
    e.preventDefault();
    const { error } = await api.POST("/api/v1/lands/{land_id}/transfers", { params: { path: { land_id: land.id } },
      body: { new_owner_npi: transfer.new_owner_npi, reason: transfer.reason as never, note: transfer.note || undefined } });
    error ? fail(error) : done("Demande de transfert envoyée : un agent va la vérifier.");
  };
  const remove = async () => {
    if (!window.confirm("Supprimer définitivement cette parcelle et ses récoltes ?")) return;
    const { error } = await api.DELETE("/api/v1/lands/{land_id}", { params: { path: { land_id: land.id } } });
    if (error) return fail(error);
    qc.invalidateQueries({ queryKey: ["lands"] });
    navigate("/cadastre");
  };

  return (
    <Card>
      <CardHeader title="Gérer la parcelle" />
      <div className="flex flex-wrap gap-2">
        <Link to={`/cadastre/${land.id}/contour`} className={buttonClass("outline")}><MapPin className="w-4 h-4" aria-hidden /> Refaire le contour</Link>
        <Button variant="outline" onClick={() => setPanel(panel === "edit" ? null : "edit")}><Pencil className="w-4 h-4" aria-hidden /> Modifier les informations</Button>
        <Button variant="outline" onClick={() => setPanel(panel === "transfer" ? null : "transfer")}><ArrowLeftRight className="w-4 h-4" aria-hidden /> Transférer</Button>
        <Button variant="danger" onClick={remove}><Trash2 className="w-4 h-4" aria-hidden /> Supprimer</Button>
      </div>
      {land.verification_status === "verifiee" && <p className="text-xs text-neutral-500 mt-2">Refaire le contour annule la vérification : un agent devra revenir.</p>}
      {panel === "edit" && (
        <form onSubmit={save} className="grid gap-3 sm:grid-cols-3 items-end mt-4">
          <Field id="ecrop" label="Culture"><input id="ecrop" value={edit.crop_type} onChange={(e) => setEdit({ ...edit, crop_type: e.target.value })} className={inputCls} /></Field>
          <Field id="eyield" label="Récolte prévue (kg)"><input id="eyield" inputMode="numeric" value={edit.estimated_yield_kg} onChange={(e) => setEdit({ ...edit, estimated_yield_kg: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <Field id="eloc" label="Village"><input id="eloc" value={edit.locality} onChange={(e) => setEdit({ ...edit, locality: e.target.value })} className={inputCls} /></Field>
          <Button type="submit" className="sm:col-span-3">Enregistrer</Button>
        </form>
      )}
      {panel === "transfer" && (
        <form onSubmit={requestTransfer} className="grid gap-3 sm:grid-cols-2 items-end mt-4">
          <Field id="tnpi" label="NPI du nouveau propriétaire"><input id="tnpi" inputMode="numeric" maxLength={10} value={transfer.new_owner_npi} onChange={(e) => setTransfer({ ...transfer, new_owner_npi: e.target.value.replace(/\D/g, "") })} className={`${inputCls} tabular-nums`} /></Field>
          <Field id="treason" label="Motif">
            <select id="treason" value={transfer.reason} onChange={(e) => setTransfer({ ...transfer, reason: e.target.value })} className={inputCls}>
              <option value="vente">Vente</option><option value="heritage">Héritage</option><option value="donation">Donation</option><option value="autre">Autre</option>
            </select>
          </Field>
          <div className="sm:col-span-2"><Field id="tnote" label="Précisions (facultatif)"><input id="tnote" value={transfer.note} onChange={(e) => setTransfer({ ...transfer, note: e.target.value })} className={inputCls} /></Field></div>
          <Button type="submit" className="sm:col-span-2" disabled={transfer.new_owner_npi.length !== 10}>Demander le transfert</Button>
        </form>
      )}
      {msg && <div className="mt-3"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
    </Card>
  );
}

function AgentVerification({ land }: { land: Land }) {
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const verify = useMutation({
    mutationFn: async (status: "verifiee" | "rejetee") => unwrap(await api.PATCH("/api/v1/lands/{land_id}/verification", { params: { path: { land_id: land.id } }, body: { status, note } })),
    onSuccess: () => { setNote(""); qc.invalidateQueries({ queryKey: ["land", land.id] }); },
  });
  return (
    <Card>
      <CardHeader icon={ClipboardCheck} title="Vérification de terrain" />
      {land.verification_status !== "declaree" && (
        <p className="text-sm mb-3">Statut : <strong>{land.verification_status === "verifiee" ? "vérifiée" : "non validée"}</strong>{land.verification_note ? ` · ${land.verification_note}` : ""}{land.verified_at ? ` (${formatDate(land.verified_at)})` : ""}</p>
      )}
      <Field id="vnote" label="Constat de la visite"><textarea id="vnote" rows={2} value={note} onChange={(e) => setNote(e.target.value)} className={inputCls} placeholder="Ex. : bornes conformes au contour, culture en place" /></Field>
      <div className="flex flex-wrap gap-2 mt-3">
        <Button onClick={() => verify.mutate("verifiee")} disabled={note.trim().length < 3} loading={verify.isPending}>Valider la parcelle</Button>
        <Button variant="danger" onClick={() => verify.mutate("rejetee")} disabled={note.trim().length < 3}>Ne pas valider</Button>
      </div>
      {verify.isError && <div className="mt-3"><Alert tone="error">{(verify.error as Error).message}</Alert></div>}
    </Card>
  );
}

export function ParcelDetailPage() {
  const { id } = useParams();
  const { user } = useSession();
  const land = useQuery({ queryKey: ["land", id], queryFn: async () => unwrap(await api.GET("/api/v1/lands/{land_id}", { params: { path: { land_id: id! } } })) });
  const l = land.data;
  const fc = useMemo<GeoJSON.FeatureCollection | undefined>(() => l && ({ type: "FeatureCollection",
    features: [{ type: "Feature", properties: { id: l.id, dispute_flag: l.dispute_flag, verification_status: l.verification_status }, geometry: l.boundary as unknown as GeoJSON.Geometry }] }), [l]);
  const fit = useMemo(() => featureBounds(fc), [fc]);
  if (land.isLoading) return <Loading />;
  if (land.isError || !l) return <Alert tone="error">{(land.error as Error)?.message ?? "Parcelle introuvable."}</Alert>;
  const owner = l.npi_owner === user?.npi;
  const agent = user?.role === "state_agent" || user?.role === "state_supervisor";

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-12 h-12 rounded-lg bg-emerald-100 border border-emerald-200 flex items-center justify-center shrink-0"><Sprout className="w-6 h-6 text-emerald-800" aria-hidden /></div>
            <div className="min-w-0">
              <p className="text-xs font-bold text-emerald-800">{l.cadastral_reference ?? `Parcelle ${l.id.slice(-6).toUpperCase()}`}</p>
              <h1 className="text-xl font-bold">{l.crop_type}{l.locality ? ` · ${l.locality}` : ""}</h1>
              <p className="text-sm text-neutral-600">{l.commune} ({l.department})</p>
            </div>
          </div>
          <StatusBadge land={l} />
        </div>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-5 pt-5 border-t border-neutral-100 text-sm">
          <div><dt className="text-neutral-500 text-xs">Surface calculée</dt><dd className="text-lg font-bold tabular-nums">{formatNumber(l.surface_hectares, 2)} ha</dd></div>
          <div><dt className="text-neutral-500 text-xs">Périmètre</dt><dd className="text-lg font-bold tabular-nums">{formatNumber(l.perimeter_m)} m</dd></div>
          <div><dt className="text-neutral-500 text-xs">Récolte prévue</dt><dd className="text-lg font-bold tabular-nums">{formatNumber(l.estimated_yield_kg / 1000, 1)} t</dd></div>
          <div><dt className="text-neutral-500 text-xs">Relevé</dt><dd className="font-semibold">{CAPTURE[l.capture_method] ?? l.capture_method}</dd>
            <dd className="text-xs text-neutral-500">{l.points_count} points{l.gps_accuracy_mean_m ? ` · précision ${formatNumber(l.gps_accuracy_mean_m)} m` : ""}</dd></div>
        </dl>
      </Card>

      <MapView className="h-80" parcels={fc} fitBounds={fit} label="Contour de la parcelle" />
      {owner && <OwnerActions land={l} />}
      {agent && <AgentVerification land={l} />}
      <Disputes land={l} />
      <Harvests land={l} owner={owner} />
      <SoilAndFertilization land={l} owner={owner} />
      {l.ownership_history && l.ownership_history.length > 0 && (
        <Card>
          <CardHeader icon={ArrowLeftRight} title="Historique des propriétaires" />
          <ul className="text-sm space-y-1">{l.ownership_history.map((h, i) => <li key={i}>Transfert ({String((h as Record<string, unknown>).reason)}) le {formatDate(String((h as Record<string, unknown>).at))}</li>)}</ul>
        </Card>
      )}
      <WeatherWidget landId={l.id} />
      {!owner && !agent && <Empty>Vous consultez une parcelle qui ne vous appartient pas.</Empty>}
    </div>
  );
}
