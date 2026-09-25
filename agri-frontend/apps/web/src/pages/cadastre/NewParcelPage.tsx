import { api, apiErrorMessage, enqueue, newClientRef, useSession } from "@agri/core";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CloudOff, MapPin } from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Alert, Button, buttonClass, Card, CardHeader } from "../../components/ui";
import { COMMON_CROPS, DEPARTMENTS } from "../../lib/benin";
import { type CapturedPoint, CaptureBoundary, type CaptureMethod, captureProblems } from "./CaptureBoundary";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";

interface Result {
  id: string;
  status: string;
  surface_hectares: number;
  warnings?: string[];
  overlaps?: { overlap_m2: number; land_id?: string | null; domain_id?: string | null }[];
}

function ResultCard({ result, onAnother }: { result: Result; onAnother?: () => void }) {
  const dispute = result.status.includes("dispute");
  return (
    <Card>
      <div className="flex items-start gap-3">
        {dispute ? <AlertTriangle className="w-6 h-6 text-red-600 shrink-0" aria-hidden /> : <CheckCircle2 className="w-6 h-6 text-emerald-700 shrink-0" aria-hidden />}
        <div className="space-y-2 min-w-0">
          <h1 className="text-lg font-bold">{result.status === "already_registered" ? "Parcelle déjà enregistrée" : result.status.startsWith("updated") ? "Contour mis à jour" : "Parcelle enregistrée"}</h1>
          <p className="text-sm">Surface calculée par le serveur : <strong className="tabular-nums">{result.surface_hectares.toLocaleString("fr-FR")} ha</strong></p>
          {dispute && <Alert tone="error">Le contour chevauche une autre parcelle ou une terre de l'État. Un litige a été ouvert : un agent va examiner la situation.</Alert>}
          {result.warnings?.map((w) => <Alert key={w} tone="warning">{w}</Alert>)}
          <div className="flex flex-wrap gap-2 pt-1">
            <Link to={`/cadastre/${result.id}`} className={buttonClass("primary")}>Voir la parcelle</Link>
            {onAnother && <Button variant="outline" onClick={onAnother}>Enregistrer une autre parcelle</Button>}
          </div>
        </div>
      </div>
    </Card>
  );
}

/** Nouvelle parcelle (/cadastre/nouvelle) ou nouveau contour d'une parcelle existante (/cadastre/:id/contour). */
export function NewParcelPage() {
  const { id } = useParams();
  const editing = !!id;
  const { user } = useSession();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const draftKey = `agrismart.draft.${id ?? "nouvelle"}`;
  const [points, setPoints] = useState<CapturedPoint[]>([]);
  const [method, setMethod] = useState<CaptureMethod>("gps_walk");
  const [form, setForm] = useState({ department: "", commune: user?.commune ?? "", locality: "", crop_type: "", estimated_yield_kg: "", cadastral_reference: "" });
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [sending, setSending] = useState(false);
  const [resetKey, setResetKey] = useState(0);

  const onCapture = useCallback((p: CapturedPoint[], m: CaptureMethod) => {
    setPoints(p);
    setMethod(m);
  }, []);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const finish = (r: Result) => {
    localStorage.removeItem(draftKey);
    qc.invalidateQueries({ queryKey: ["lands"] });
    setResult(r);
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const problem = captureProblems(points);
    if (problem) return setError(problem);
    const boundary = { points, capture_method: method };
    setSending(true);
    try {
      if (editing) {
        const { data, error: err } = await api.PUT("/api/v1/lands/{land_id}/boundary", { params: { path: { land_id: id! } }, body: boundary });
        if (err) return setError(apiErrorMessage(err));
        return finish(data as Result);
      }
      const body = {
        department: form.department, commune: form.commune, locality: form.locality || undefined, crop_type: form.crop_type,
        estimated_yield_kg: Number(form.estimated_yield_kg), cadastral_reference: form.cadastral_reference || undefined,
        boundary, client_ref: newClientRef(),
      };
      try {
        const { data, error: err } = await api.POST("/api/v1/lands/", { body: body as never });
        if (err) return setError(apiErrorMessage(err));
        finish(data as Result);
      } catch {
        // Pas de réseau : la parcelle part plus tard, sans doublon grâce au client_ref
        await enqueue("land", `Parcelle de ${form.crop_type.toLowerCase()} (${form.commune})`, body);
        localStorage.removeItem(draftKey);
        setQueued(true);
      }
    } finally {
      setSending(false);
    }
  }

  if (result) {
    return <ResultCard result={result} onAnother={editing ? undefined : () => { setResult(null); setResetKey((k) => k + 1); }} />;
  }
  if (queued) {
    return (
      <Card>
        <div className="flex items-start gap-3">
          <CloudOff className="w-6 h-6 text-amber-700 shrink-0" aria-hidden />
          <div className="space-y-2">
            <h1 className="text-lg font-bold">Parcelle gardée sur le téléphone</h1>
            <p className="text-sm text-neutral-700">Pas de réseau pour l'instant. Elle sera envoyée automatiquement dès le retour de la connexion ; vous serez prévenu en cas de problème.</p>
            <Button variant="outline" onClick={() => navigate("/")}>Revenir à l'accueil</Button>
          </div>
        </div>
      </Card>
    );
  }

  const canSubmit = points.length >= 3 && (editing || (form.department && form.commune.trim().length >= 2 && form.crop_type.trim().length >= 2 && form.estimated_yield_kg !== ""));
  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <Card>
        <CardHeader icon={MapPin} title={editing ? "Nouveau contour de la parcelle" : "1. Relever le contour du champ"} />
        <CaptureBoundary key={resetKey} draftKey={draftKey} onChange={onCapture} />
      </Card>

      {!editing && (
        <Card>
          <CardHeader title="2. Informations sur la parcelle" />
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="dep" className="block text-sm font-semibold mb-1">Département</label>
              <select id="dep" value={form.department} onChange={set("department")} className={inputCls} required>
                <option value="">Choisir…</option>
                {DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="com" className="block text-sm font-semibold mb-1">Commune</label>
              <input id="com" value={form.commune} onChange={set("commune")} className={inputCls} required />
            </div>
            <div>
              <label htmlFor="loc" className="block text-sm font-semibold mb-1">Village ou arrondissement <span className="font-normal text-neutral-500">(facultatif)</span></label>
              <input id="loc" value={form.locality} onChange={set("locality")} className={inputCls} />
            </div>
            <div>
              <label htmlFor="crop" className="block text-sm font-semibold mb-1">Culture principale</label>
              <input id="crop" list="crops" value={form.crop_type} onChange={set("crop_type")} className={inputCls} required />
              <datalist id="crops">{COMMON_CROPS.map((c) => <option key={c} value={c} />)}</datalist>
            </div>
            <div>
              <label htmlFor="yield" className="block text-sm font-semibold mb-1">Récolte prévue sur la parcelle (kg)</label>
              <input id="yield" inputMode="numeric" value={form.estimated_yield_kg} onChange={(e) => setForm((f) => ({ ...f, estimated_yield_kg: e.target.value.replace(/\D/g, "") }))} className={`${inputCls} tabular-nums`} required />
            </div>
            <div>
              <label htmlFor="ref" className="block text-sm font-semibold mb-1">Référence cadastrale <span className="font-normal text-neutral-500">(si vous en avez une)</span></label>
              <input id="ref" value={form.cadastral_reference} onChange={set("cadastral_reference")} className={inputCls} />
            </div>
          </div>
        </Card>
      )}

      {error && <Alert tone="error">{error}</Alert>}
      <Button type="submit" className="w-full min-h-14 text-base" loading={sending} disabled={!canSubmit}>
        {editing ? "Enregistrer le nouveau contour" : "Enregistrer la parcelle"}
      </Button>
    </form>
  );
}
