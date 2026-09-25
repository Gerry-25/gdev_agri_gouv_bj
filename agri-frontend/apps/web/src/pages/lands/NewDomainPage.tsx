import { api, apiErrorMessage } from "@agri/core";
import { useCallback, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Alert, Button, buttonClass, Card, CardHeader } from "../../components/ui";
import { DEPARTMENTS } from "../../lib/benin";
import { type CapturedPoint, CaptureBoundary, type CaptureMethod, captureProblems } from "../cadastre/CaptureBoundary";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";

/** Enregistrement d'une terre du domaine privé de l'État (contour GPS ou tracé sur la carte). */
export function NewDomainPage() {
  const [points, setPoints] = useState<CapturedPoint[]>([]);
  const [method, setMethod] = useState<CaptureMethod>("gps_walk");
  const [f, setF] = useState({ name: "", department: "", commune: "", locality: "", land_title_ref: "", suitable_crops: "", description: "" });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ id: string; surface_hectares: number; warnings?: string[]; status: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const onCapture = useCallback((p: CapturedPoint[], m: CaptureMethod) => { setPoints(p); setMethod(m); }, []);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const problem = captureProblems(points);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    const { data, error: err } = await api.POST("/api/v1/domains", { body: {
      name: f.name, department: f.department, commune: f.commune, locality: f.locality || undefined, land_title_ref: f.land_title_ref || undefined,
      suitable_crops: f.suitable_crops.split(",").map((c) => c.trim()).filter(Boolean), description: f.description || undefined,
      boundary: { points, capture_method: method === "map_drawing" ? "map_drawing" : "gps_walk" },
    } as never });
    setBusy(false);
    if (err) return setError(apiErrorMessage(err));
    localStorage.removeItem("agrismart.draft.domaine");
    setResult(data as never);
  };
  if (result) {
    return (
      <Card className="space-y-3">
        <h1 className="text-lg font-bold">Terre enregistrée</h1>
        <p className="text-sm">Surface calculée : <strong>{result.surface_hectares.toLocaleString("fr-FR")} ha</strong></p>
        {result.warnings?.map((w) => <Alert key={w} tone="warning">{w}</Alert>)}
        <Link to={`/concessions/terres/${result.id}`} className={buttonClass("primary")}>Préparer le plan de mise en valeur</Link>
      </Card>
    );
  }
  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <Card><CardHeader title="1. Contour de la terre" /><CaptureBoundary draftKey="agrismart.draft.domaine" onChange={onCapture} /></Card>
      <Card>
        <CardHeader title="2. Identification" />
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2"><label htmlFor="dn" className="block text-sm font-semibold mb-1">Nom</label><input id="dn" value={f.name} onChange={set("name")} className={inputCls} placeholder="Ferme domaniale de…" /></div>
          <div><label htmlFor="dd" className="block text-sm font-semibold mb-1">Département</label><select id="dd" value={f.department} onChange={set("department")} className={inputCls}><option value="">Choisir…</option>{DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}</select></div>
          <div><label htmlFor="dc" className="block text-sm font-semibold mb-1">Commune</label><input id="dc" value={f.commune} onChange={set("commune")} className={inputCls} /></div>
          <div><label htmlFor="dl" className="block text-sm font-semibold mb-1">Localité</label><input id="dl" value={f.locality} onChange={set("locality")} className={inputCls} /></div>
          <div><label htmlFor="dt" className="block text-sm font-semibold mb-1">Référence du titre foncier</label><input id="dt" value={f.land_title_ref} onChange={set("land_title_ref")} className={inputCls} /></div>
          <div className="sm:col-span-2"><label htmlFor="ds" className="block text-sm font-semibold mb-1">Cultures jugées adaptées (séparées par des virgules)</label><input id="ds" value={f.suitable_crops} onChange={set("suitable_crops")} className={inputCls} /></div>
          <div className="sm:col-span-2"><label htmlFor="ddesc" className="block text-sm font-semibold mb-1">Description</label><textarea id="ddesc" rows={3} value={f.description} onChange={set("description")} className={inputCls} /></div>
        </div>
      </Card>
      {error && <Alert tone="error">{error}</Alert>}
      <Button type="submit" className="w-full min-h-12" loading={busy} disabled={points.length < 3 || f.name.length < 3 || !f.department || f.commune.length < 2}>Enregistrer la terre</Button>
    </form>
  );
}
