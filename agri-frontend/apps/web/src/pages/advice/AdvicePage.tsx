import { api, apiErrorMessage, type components, formatDate, formatRelative, useSession } from "@agri/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, BookOpen, Mic, Pencil, Plus, Search, Send, Square, Trash2 } from "lucide-react";
import { Fragment, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { AudioButton } from "../../components/AudioButton";
import { Alert, Badge, Button, Card, CardHeader, Empty, Loading } from "../../components/ui";
import { unwrap } from "../../lib/queries";

type Guide = components["schemas"]["GuideOut"];
interface Answer { id: string; question: string; answer: string; simple_summary: string; covered: boolean; follow_up?: string | null; transcript?: string;
  sources: { slug: string; title: string; verified: boolean; source?: string }[]; created_at: string }

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";

/** Rendu sûr d'un texte de fiche : paragraphes, listes « - » et **gras**, sans HTML injecté. */
function RichText({ text }: { text: string }) {
  const inline = (s: string) => s.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <Fragment key={i}>{p}</Fragment>));
  return (
    <div className="space-y-2">
      {text.split(/\n{2,}/).map((block, i) => {
        const lines = block.split("\n");
        if (lines.every((l) => l.trim().startsWith("- "))) return <ul key={i} className="list-disc pl-5 space-y-0.5">{lines.map((l, j) => <li key={j}>{inline(l.trim().slice(2))}</li>)}</ul>;
        if (block.startsWith("#")) return <h4 key={i} className="font-bold">{inline(block.replace(/^#+\s*/, ""))}</h4>;
        return <p key={i}>{inline(block)}</p>;
      })}
    </div>
  );
}

// --- Assistant --------------------------------------------------------------------------

function useRecorder(maxSeconds = 60) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const resolver = useRef<((b: Blob | null) => void) | null>(null);
  useEffect(() => {
    if (!recording) return;
    const t = window.setInterval(() => setSeconds((s) => {
      if (s + 1 >= maxSeconds) rec.current?.stop();
      return s + 1;
    }), 1000);
    return () => window.clearInterval(t);
  }, [recording, maxSeconds]);
  const start = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find((m) => MediaRecorder.isTypeSupported(m));
    const r = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunks.current = [];
    r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    r.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      setRecording(false);
      resolver.current?.(chunks.current.length ? new Blob(chunks.current, { type: r.mimeType.split(";")[0] }) : null);
    };
    rec.current = r;
    setSeconds(0);
    r.start();
    setRecording(true);
  };
  const stop = () => new Promise<Blob | null>((resolve) => { resolver.current = resolve; rec.current?.stop(); });
  return { recording, seconds, start, stop, supported: typeof window !== "undefined" && "MediaRecorder" in window && !!navigator.mediaDevices };
}

function AnswerCard({ a }: { a: Answer }) {
  return (
    <div className="space-y-2">
      <p className="p-2.5 rounded bg-neutral-100 text-sm"><span className="font-semibold">Vous : </span>{a.transcript ?? a.question}</p>
      <div className={`p-3 rounded-lg border text-sm space-y-2 ${a.covered ? "border-emerald-200 bg-emerald-50/50" : "border-amber-200 bg-amber-50"}`}>
        <p className="text-base font-semibold">{a.simple_summary}</p>
        {a.covered && a.answer !== a.simple_summary && <RichText text={a.answer} />}
        {a.follow_up && <p className="text-neutral-700">{a.follow_up}</p>}
        {!!a.sources.length && (
          <p className="text-xs text-neutral-600">Source{a.sources.length > 1 ? "s" : ""} : {a.sources.map((s) => `${s.title}${s.verified ? " (fiche validée)" : " (exemple non validé)"}`).join(" ; ")}</p>
        )}
        {a.covered && <AudioButton path={{ kind: "assistant", id: a.id }} label="Écouter la réponse" />}
      </div>
    </div>
  );
}

function Assistant() {
  const { user } = useSession();
  const qc = useQueryClient();
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const recorder = useRecorder();
  const history = useQuery({ queryKey: ["assistant", "history"], queryFn: async () => unwrap(await api.GET("/api/v1/assistant/history", { params: { query: { limit: 5 } } })) as unknown as Answer[] });
  const ask = useMutation({
    mutationFn: async (input: { text?: string; audio?: Blob }) => {
      const preferred = (user?.preferred_language as "fr" | "fon" | "yo" | "en") ?? "fr";
      if (input.audio) {
        const form = new FormData();
        form.append("file", input.audio, `question.${input.audio.type.includes("mp4") ? "m4a" : input.audio.type.includes("ogg") ? "ogg" : "webm"}`);
        form.append("language", preferred);
        const { data, error } = await api.POST("/api/v1/assistant/ask-voice", { body: form as never });
        if (error) throw new Error(apiErrorMessage(error));
        return data as unknown as Answer;
      }
      const { data, error } = await api.POST("/api/v1/assistant/ask", { body: { question: input.text!, language: preferred } });
      if (error) throw new Error(apiErrorMessage(error));
      return data as unknown as Answer;
    },
    onSuccess: (a) => { setAnswers((x) => [...x, a]); setQuestion(""); qc.invalidateQueries({ queryKey: ["assistant"] }); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); if (question.trim().length >= 5) ask.mutate({ text: question }); };
  const voice = async () => {
    if (recorder.recording) {
      const audio = await recorder.stop();
      if (audio) ask.mutate({ audio });
    } else {
      try { await recorder.start(); } catch { /* micro refusé */ }
    }
  };
  return (
    <Card className="space-y-4">
      <CardHeader icon={Mic} title="Posez votre question" />
      <p className="text-sm text-neutral-600">L'assistant répond à partir des fiches validées par les services agricoles. S'il n'a pas la réponse, il vous le dit.</p>
      {answers.map((a) => <AnswerCard key={a.id} a={a} />)}
      <form onSubmit={submit} className="flex flex-col sm:flex-row gap-2">
        <label htmlFor="aq" className="sr-only">Votre question</label>
        <input id="aq" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} className={`${inputCls} flex-1`} placeholder="Ex. : comment enregistrer ma parcelle avec le GPS ?" />
        <div className="flex gap-2">
          <Button type="submit" loading={ask.isPending && !recorder.recording} disabled={question.trim().length < 5}><Send className="w-4 h-4" aria-hidden /> Envoyer</Button>
          {recorder.supported && (
            <Button variant={recorder.recording ? "danger" : "soft"} onClick={voice} disabled={ask.isPending} aria-label={recorder.recording ? "Arrêter et envoyer" : "Poser la question à voix haute"}>
              {recorder.recording ? <><Square className="w-4 h-4" aria-hidden /> {recorder.seconds} s</> : <><Mic className="w-4 h-4" aria-hidden /> Parler</>}
            </Button>
          )}
        </div>
      </form>
      {recorder.recording && <p className="text-sm text-red-700" aria-live="polite">Enregistrement en cours… appuyez sur le bouton rouge pour envoyer (60 s maximum).</p>}
      {ask.isPending && <p className="text-sm text-neutral-600">Recherche dans les fiches…</p>}
      {ask.isError && <Alert tone="error">{(ask.error as Error).message}</Alert>}
      {!answers.length && !!history.data?.length && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold text-emerald-800 min-h-11 flex items-center">Mes questions récentes</summary>
          <ul className="space-y-1">{history.data.map((h) => <li key={h.id}><span className="font-semibold">{h.question}</span> <span className="text-neutral-500">({formatRelative(h.created_at)})</span><br />{h.simple_summary}</li>)}</ul>
        </details>
      )}
    </Card>
  );
}

// --- Fiches ------------------------------------------------------------------------------

function GuideEditor({ guide, onDone }: { guide?: Guide; onDone: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    slug: guide?.slug ?? "", title: guide?.title ?? "", category: guide?.category ?? "bonnes_pratiques", summary: guide?.summary ?? "", steps: (guide?.steps ?? []).join("\n"),
    content: guide?.content ?? "", pictogram: guide?.pictogram ?? "info", crops: (guide?.crops ?? []).join(", "), source: guide?.source ?? "", source_url: guide?.source_url ?? "", verified: guide?.verified ?? false,
  });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const save = useMutation({
    mutationFn: async () => {
      const body = { title: f.title, category: f.category as never, summary: f.summary, steps: f.steps.split("\n").map((s) => s.trim()).filter(Boolean), content: f.content,
        pictogram: f.pictogram, crops: f.crops.split(",").map((c) => c.trim()).filter(Boolean), source: f.source, source_url: f.source_url || undefined, verified: f.verified };
      const res = guide ? await api.PUT("/api/v1/knowledge/guides/{slug}", { params: { path: { slug: guide.slug } }, body })
        : await api.POST("/api/v1/knowledge/guides", { body: { ...body, slug: f.slug } });
      if (res.error) throw new Error(apiErrorMessage(res.error));
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["knowledge"] }); onDone(); },
  });
  const L = ({ id, label, children, wide }: { id: string; label: string; children: ReactNode; wide?: boolean }) => <div className={wide ? "sm:col-span-2" : ""}><label htmlFor={id} className="block text-sm font-semibold mb-1">{label}</label>{children}</div>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="grid gap-3 sm:grid-cols-2 p-3 rounded-lg border border-neutral-200 bg-neutral-50">
      {!guide && <L id="g-slug" label="Identifiant (minuscules et tirets)"><input id="g-slug" value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} className={inputCls} /></L>}
      <L id="g-title" label="Titre"><input id="g-title" value={f.title} onChange={set("title")} className={inputCls} /></L>
      <L id="g-cat" label="Catégorie"><select id="g-cat" value={f.category} onChange={set("category")} className={inputCls}>
        <option value="produits_interdits">Produits interdits</option><option value="normes_sanitaires">Normes sanitaires</option><option value="reglementation">Lois et démarches</option><option value="bonnes_pratiques">Bonnes pratiques</option><option value="faq">Questions fréquentes</option></select></L>
      <L id="g-crops" label="Cultures concernées (vide = toutes)"><input id="g-crops" value={f.crops} onChange={set("crops")} className={inputCls} /></L>
      <L id="g-sum" label="Résumé en mots simples (lu à voix haute)" wide><textarea id="g-sum" rows={2} value={f.summary} onChange={set("summary")} className={inputCls} /></L>
      <L id="g-steps" label="Étapes (une par ligne)" wide><textarea id="g-steps" rows={4} value={f.steps} onChange={set("steps")} className={inputCls} /></L>
      <L id="g-content" label="Texte détaillé (« - » pour une liste, **gras**)" wide><textarea id="g-content" rows={4} value={f.content} onChange={set("content")} className={inputCls} /></L>
      <L id="g-src" label="Source (texte officiel ou organisme)"><input id="g-src" value={f.source} onChange={set("source")} className={inputCls} /></L>
      <L id="g-url" label="Lien vers la source"><input id="g-url" type="url" value={f.source_url} onChange={set("source_url")} className={inputCls} /></L>
      <label className="sm:col-span-2 flex items-center gap-2 min-h-11 text-sm"><input type="checkbox" className="w-5 h-5 accent-emerald-800" checked={f.verified} onChange={(e) => setF({ ...f, verified: e.target.checked })} />
        Contenu validé par un service habilité (l'assistant ne s'appuie que sur les fiches validées)</label>
      {save.isError && <div className="sm:col-span-2"><Alert tone="error">{(save.error as Error).message}</Alert></div>}
      <div className="sm:col-span-2 flex gap-2"><Button type="submit" loading={save.isPending} disabled={f.title.length < 3 || f.summary.length < 10 || f.source.length < 3}>Enregistrer</Button><Button variant="ghost" onClick={onDone}>Annuler</Button></div>
    </form>
  );
}

function GuideItem({ g, agent }: { g: Guide; agent: boolean }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const remove = async () => {
    if (!window.confirm("Supprimer cette fiche ?")) return;
    await api.DELETE("/api/v1/knowledge/guides/{slug}", { params: { path: { slug: g.slug } } });
    qc.invalidateQueries({ queryKey: ["knowledge"] });
  };
  if (editing) return <li><GuideEditor guide={g} onDone={() => setEditing(false)} /></li>;
  return (
    <li className="border border-neutral-200 rounded-lg bg-white">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="w-full p-4 text-left cursor-pointer space-y-1">
        <span className="flex flex-wrap items-start justify-between gap-2">
          <span className="font-bold">{g.title}</span>
          {g.verified ? <Badge tone="green"><BadgeCheck className="w-3.5 h-3.5" aria-hidden /> Validée</Badge> : <Badge tone="amber">Exemple à valider</Badge>}
        </span>
        <span className="block text-sm text-neutral-700">{g.summary}</span>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-3 text-sm border-t border-neutral-100 pt-3">
          <AudioButton path={{ kind: "guide", slug: g.slug }} label="Écouter la fiche" />
          {!!g.steps?.length && <ol className="space-y-1.5">{g.steps.map((s, i) => <li key={i} className="flex gap-3"><span className="w-6 h-6 rounded-full bg-emerald-800 text-white text-xs font-bold grid place-items-center shrink-0 tabular-nums">{i + 1}</span><span className="pt-0.5">{s}</span></li>)}</ol>}
          {g.content && <RichText text={g.content} />}
          <p className="text-xs text-neutral-500">Source : {g.source}{g.source_url ? <> · <a href={g.source_url} target="_blank" rel="noopener noreferrer" className="underline">voir le texte</a></> : null} · mise à jour le {formatDate(g.updated_at)}</p>
          {agent && <div className="flex gap-2"><Button variant="outline" onClick={() => setEditing(true)}><Pencil className="w-4 h-4" aria-hidden /> Modifier</Button><Button variant="danger" onClick={remove}><Trash2 className="w-4 h-4" aria-hidden /> Supprimer</Button></div>}
        </div>
      )}
    </li>
  );
}

function Guides() {
  const { user } = useSession();
  const agent = user?.role === "state_agent" || user?.role === "state_supervisor";
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const cats = useQuery({ queryKey: ["knowledge", "categories"], queryFn: async () => unwrap(await api.GET("/api/v1/knowledge/categories")) as unknown as { id: string; label: string; count: number }[] });
  const guides = useQuery({
    queryKey: ["knowledge", "guides", category, q],
    queryFn: async () => unwrap(await api.GET("/api/v1/knowledge/guides", { params: { query: { category: (category || undefined) as never, q: q.length >= 3 ? q : undefined } } })),
  });
  return (
    <Card className="space-y-4">
      <CardHeader icon={BookOpen} title="Fiches pratiques et réglementation" action={agent && !creating ? <Button className="min-h-9" onClick={() => setCreating(true)}><Plus className="w-4 h-4" aria-hidden /> Nouvelle fiche</Button> : undefined} />
      {creating && <GuideEditor onDone={() => setCreating(false)} />}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Catégories">
        <button type="button" aria-pressed={!category} onClick={() => setCategory("")} className={`min-h-9 px-3 rounded-full border text-sm font-semibold cursor-pointer ${!category ? "bg-emerald-800 border-emerald-800 text-white" : "border-neutral-300 text-neutral-700"}`}>Toutes</button>
        {cats.data?.map((c) => (
          <button key={c.id} type="button" aria-pressed={category === c.id} onClick={() => setCategory(c.id)}
                  className={`min-h-9 px-3 rounded-full border text-sm font-semibold cursor-pointer ${category === c.id ? "bg-emerald-800 border-emerald-800 text-white" : "border-neutral-300 text-neutral-700"}`}>{c.label} ({c.count})</button>
        ))}
      </div>
      <div className="relative">
        <Search className="w-4 h-4 text-neutral-400 absolute left-3 top-3.5" aria-hidden />
        <label htmlFor="gq" className="sr-only">Rechercher une fiche</label>
        <input id="gq" value={q} onChange={(e) => setQ(e.target.value)} className={`${inputCls} pl-9`} placeholder="Rechercher (neem, récolte, litige…)" />
      </div>
      {guides.isLoading && <Loading />}
      {guides.isSuccess && !guides.data.length && <Empty>Aucune fiche ne correspond.</Empty>}
      <ul className="space-y-3">{guides.data?.map((g) => <GuideItem key={g.slug} g={g} agent={agent} />)}</ul>
    </Card>
  );
}

export function AdvicePage() {
  return (
    <div className="space-y-5">
      <Card>
        <h1 className="text-xl font-bold tracking-tight">Conseils</h1>
        <p className="text-sm text-neutral-600">Bonnes pratiques, normes sanitaires, produits interdits et démarches, avec un assistant qui répond à la voix.</p>
      </Card>
      <Assistant />
      <Guides />
    </div>
  );
}
