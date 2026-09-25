import { api, apiErrorMessage, enqueue, formatRelative, newClientRef, useSession } from "@agri/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CloudOff, History, LocateFixed, ScanLine, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { DiagnosisPhoto } from "../../components/AuthImage";
import { Alert, Badge, Button, Card, CardHeader, Empty, Loading } from "../../components/ui";
import { COMMON_CROPS, DEPARTMENTS } from "../../lib/benin";
import { compressImage } from "../../lib/image";
import { unwrap, useMyLands } from "../../lib/queries";
import { type Diagnosis, DiagnosisResult } from "./DiagnosisResult";
import { SanitaryWatch } from "./SanitaryWatch";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";

function Scanner({ onResult }: { onResult: (d: Diagnosis) => void }) {
  const { user } = useSession();
  const qc = useQueryClient();
  const lands = useMyLands();
  const [landId, setLandId] = useState("");
  const [crop, setCrop] = useState("");
  const [department, setDepartment] = useState(user?.department ?? "");
  const [commune, setCommune] = useState(user?.commune ?? "");
  const [gps, setGps] = useState<{ latitude: number; longitude: number } | null>(null);
  const [photo, setPhoto] = useState<{ blob: Blob; url: string; takenAt: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState(false);

  const land = lands.data?.find((l) => l.id === landId);
  useEffect(() => { if (land) setCrop(land.crop_type); }, [land]);
  useEffect(() => () => void (photo && URL.revokeObjectURL(photo.url)), [photo]);

  const pick = async (file?: File) => {
    if (!file) return;
    setError(null);
    try {
      const blob = await compressImage(file);
      setPhoto({ blob, url: URL.createObjectURL(blob), takenAt: file.lastModified || Date.now() });
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const locate = () => navigator.geolocation?.getCurrentPosition(
    (p) => setGps({ latitude: p.coords.latitude, longitude: p.coords.longitude }),
    () => setError("Position indisponible : indiquez la commune."),
    { enableHighAccuracy: true, timeout: 15_000 },
  );

  const submit = async () => {
    if (!photo) return;
    setBusy(true);
    setError(null);
    setQueued(false);
    const fields: Record<string, string | number | undefined> = {
      crop_hint: crop || "Maïs",
      land_id: landId || undefined,
      department: landId ? undefined : department,
      commune: landId ? undefined : commune,
      latitude: gps?.latitude, longitude: gps?.longitude,
      // Date réelle de la photo : compte pour la veille sanitaire même si l'envoi est différé
      captured_at: new Date(Math.min(photo.takenAt, Date.now())).toISOString(),
      client_ref: newClientRef(),
      language: user?.preferred_language ?? "fr",
    };
    const form = new FormData();
    Object.entries(fields).forEach(([k, v]) => v !== undefined && v !== "" && form.append(k, String(v)));
    form.append("file", photo.blob, "photo.jpg");
    try {
      const { data, error: err } = await api.POST("/api/v1/monitoring/diagnose", { body: form as never });
      if (err) return setError(apiErrorMessage(err));
      qc.invalidateQueries({ queryKey: ["diagnoses"] });
      setPhoto(null);
      onResult(data);
    } catch {
      await enqueue("diagnosis", `Diagnostic ${fields.crop_hint} (${land?.commune ?? commune})`, fields, photo.blob);
      setPhoto(null);
      setQueued(true);
    } finally {
      setBusy(false);
    }
  };

  const located = !!landId || (department && commune.trim().length >= 2);
  return (
    <Card className="space-y-5">
      <div>
        <h2 className="text-sm font-bold mb-2">1. Photographier la plante malade</h2>
        {photo ? (
          <div className="relative">
            <img src={photo.url} alt="Photo à analyser" className="w-full max-h-72 object-cover rounded border border-neutral-200" />
            <button type="button" onClick={() => setPhoto(null)} aria-label="Retirer la photo"
                    className="absolute top-2 right-2 w-10 h-10 rounded-full bg-white/90 border border-neutral-300 grid place-items-center cursor-pointer">
              <X className="w-5 h-5" aria-hidden />
            </button>
          </div>
        ) : (
          <label className="block border-2 border-dashed border-neutral-300 hover:border-emerald-700 rounded-lg p-8 text-center cursor-pointer bg-neutral-50/50 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-emerald-700">
            <Camera className="w-10 h-10 text-neutral-400 mx-auto" aria-hidden />
            <span className="block text-base font-semibold text-neutral-800 mt-2">Prendre une photo</span>
            <span className="block text-sm text-neutral-500 mt-1">Une feuille atteinte, de près, en pleine lumière</span>
            <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => pick(e.target.files?.[0])} />
          </label>
        )}
      </div>

      <div className="space-y-3 pt-4 border-t border-neutral-100">
        <h2 className="text-sm font-bold">2. Où se trouve la plante ?</h2>
        {!!lands.data?.length && (
          <div>
            <label htmlFor="dland" className="block text-sm font-semibold mb-1">Parcelle</label>
            <select id="dland" value={landId} onChange={(e) => setLandId(e.target.value)} className={inputCls}>
              <option value="">Autre endroit</option>
              {lands.data.map((l) => <option key={l.id} value={l.id}>{l.crop_type} · {l.locality ?? l.commune} ({l.surface_hectares.toLocaleString("fr-FR")} ha)</option>)}
            </select>
          </div>
        )}
        {!landId && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="ddep" className="block text-sm font-semibold mb-1">Département</label>
              <select id="ddep" value={department} onChange={(e) => setDepartment(e.target.value)} className={inputCls}>
                <option value="">Choisir…</option>
                {DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="dcom" className="block text-sm font-semibold mb-1">Commune</label>
              <input id="dcom" value={commune} onChange={(e) => setCommune(e.target.value)} className={inputCls} />
            </div>
          </div>
        )}
        <div>
          <label htmlFor="dcrop" className="block text-sm font-semibold mb-1">Culture</label>
          <input id="dcrop" list="dcrops" value={crop} onChange={(e) => setCrop(e.target.value)} placeholder="Maïs" className={inputCls} />
          <datalist id="dcrops">{COMMON_CROPS.map((c) => <option key={c} value={c} />)}</datalist>
        </div>
        <Button variant="outline" onClick={locate}>
          <LocateFixed className="w-4 h-4" aria-hidden /> {gps ? "Position ajoutée" : "Ajouter ma position (aide la veille sanitaire)"}
        </Button>
      </div>

      {error && <Alert tone="error">{error}</Alert>}
      {queued && (
        <Alert tone="warning">
          <span className="flex items-start gap-2"><CloudOff className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />Pas de réseau : la photo est gardée sur le téléphone. Le diagnostic sera fait au retour de la connexion et apparaîtra dans l'historique.</span>
        </Alert>
      )}
      <Button className="w-full min-h-14 text-base" onClick={submit} loading={busy} disabled={!photo || !located}>
        <Sparkles className="w-5 h-5" aria-hidden /> {busy ? "Analyse en cours…" : "Analyser la photo"}
      </Button>
    </Card>
  );
}

function HistoryList({ onOpen }: { onOpen: (d: Diagnosis) => void }) {
  const q = useQuery({
    queryKey: ["diagnoses", "me"],
    queryFn: async () => unwrap(await api.GET("/api/v1/monitoring/diagnoses/me", { params: { query: { limit: 50 } } })),
  });
  if (q.isLoading) return <Loading />;
  if (!q.data?.length) return <Empty>Aucun diagnostic pour le moment.</Empty>;
  return (
    <ul className="divide-y divide-neutral-100">
      {q.data.map((d) => (
        <li key={d.alert_id}>
          <button type="button" onClick={() => onOpen(d)} className="w-full flex items-center gap-3 py-3 text-left cursor-pointer hover:bg-neutral-50">
            {d.alert_id && d.image_url ? <DiagnosisPhoto alertId={d.alert_id} className="w-14 h-14 rounded shrink-0" /> : <span className="w-14 h-14 rounded shrink-0 bg-neutral-100 grid place-items-center text-neutral-400" aria-hidden><ScanLine className="w-6 h-6" /></span>}
            <span className="flex-1 min-w-0">
              <span className="block font-semibold truncate">{d.health_status === "Sain" ? "Plante saine" : d.disease_name ?? d.health_status}</span>
              <span className="block text-sm text-neutral-600">{d.crop_identified} · {d.commune} · {d.observed_at ? formatRelative(d.observed_at) : ""}</span>
            </span>
            <Badge tone={d.alert_color === "red" ? "red" : d.alert_color === "green" ? "green" : "amber"}>{d.severity}</Badge>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function DiagnosticPage() {
  const { user } = useSession();
  const [tab, setTab] = useState<"scan" | "history">("scan");
  const [current, setCurrent] = useState<Diagnosis | null>(null);
  const agent = user?.role === "state_agent" || user?.role === "state_supervisor";
  const resultRef = useRef<HTMLDivElement>(null);
  // Sur téléphone, le résultat s'affiche sous le formulaire : on le fait venir à l'écran
  useEffect(() => {
    if (current && tab === "scan") resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [current, tab]);
  const tabs = useMemo(() => [["scan", "Nouveau diagnostic", ScanLine], ["history", "Historique", History]] as const, []);
  if (agent) return <SanitaryWatch />;

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight flex items-center gap-2"><Sparkles className="w-5 h-5 text-emerald-800" aria-hidden /> Soigner une plante</h1>
            <p className="text-sm text-neutral-600 mt-1">Photographiez une feuille malade : l'IA identifie le problème et propose un traitement adapté.</p>
          </div>
          <div role="tablist" className="flex gap-1 bg-neutral-100 p-1 rounded border border-neutral-200">
            {tabs.map(([t, label, Icon]) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => { setTab(t); setCurrent(null); }}
                      className={`min-h-10 px-3 rounded text-sm font-semibold flex items-center gap-1.5 cursor-pointer ${tab === t ? "bg-white shadow-sm text-emerald-900" : "text-neutral-600"}`}>
                <Icon className="w-4 h-4" aria-hidden /> {label}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {tab === "scan" ? (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <div className="lg:col-span-6"><Scanner onResult={setCurrent} /></div>
          <div className="lg:col-span-6 scroll-mt-20" ref={resultRef}>
            {current ? <DiagnosisResult diagnosis={current} /> : (
              <Card><CardHeader icon={Sparkles} title="Résultat" /><p className="text-sm text-neutral-600">Le diagnostic apparaîtra ici après l'analyse de la photo.</p></Card>
            )}
          </div>
        </div>
      ) : current ? (
        <div className="space-y-3">
          <Button variant="ghost" onClick={() => setCurrent(null)}>← Retour à l'historique</Button>
          <DiagnosisResult diagnosis={current} />
        </div>
      ) : (
        <Card><CardHeader icon={History} title="Mes diagnostics" /><HistoryList onOpen={setCurrent} /></Card>
      )}
    </div>
  );
}
