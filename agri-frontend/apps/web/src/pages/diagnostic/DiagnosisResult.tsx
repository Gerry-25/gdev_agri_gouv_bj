import { api, apiErrorMessage, type components, formatDate } from "@agri/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, MessageCircleQuestion, ShieldAlert } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { AudioButton } from "../../components/AudioButton";
import { DiagnosisPhoto } from "../../components/AuthImage";
import { Alert, Badge, Button, Card } from "../../components/ui";

export type Diagnosis = components["schemas"]["DiagnosisResponse"];
interface QA { question: string; answer: string; simple_summary?: string; see_advisor?: boolean }

const SEVERITY = {
  red: { box: "border-red-300 bg-red-50", text: "text-red-800", Icon: ShieldAlert },
  orange: { box: "border-orange-300 bg-orange-50", text: "text-orange-800", Icon: AlertTriangle },
  yellow: { box: "border-amber-300 bg-amber-50", text: "text-amber-900", Icon: AlertTriangle },
  green: { box: "border-emerald-300 bg-emerald-50", text: "text-emerald-900", Icon: CheckCircle2 },
} as const;

function FollowUp({ diagnosis }: { diagnosis: Diagnosis }) {
  const qc = useQueryClient();
  const [question, setQuestion] = useState("");
  const [items, setItems] = useState<QA[]>((diagnosis.qa as unknown as QA[]) ?? []);
  const ask = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/api/v1/monitoring/diagnoses/{alert_id}/ask", {
        params: { path: { alert_id: diagnosis.alert_id! } }, body: { question },
      });
      if (error) throw new Error(apiErrorMessage(error));
      return data as unknown as QA;
    },
    onSuccess: (qa) => {
      setItems((prev) => [...prev, qa]);
      setQuestion("");
      qc.invalidateQueries({ queryKey: ["diagnoses"] });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (question.trim().length >= 5) ask.mutate();
  };
  return (
    <div className="pt-4 border-t border-neutral-100 space-y-3">
      <h3 className="text-sm font-bold flex items-center gap-2"><MessageCircleQuestion className="w-4 h-4 text-emerald-800" aria-hidden /> Une question sur ce diagnostic ?</h3>
      {items.map((qa, i) => (
        <div key={i} className="space-y-1.5 text-sm">
          <p className="p-2.5 rounded bg-neutral-100 text-neutral-800"><span className="font-semibold">Vous : </span>{qa.question}</p>
          <p className="p-2.5 rounded bg-emerald-50 border border-emerald-100 text-neutral-900">{qa.answer}</p>
          {qa.see_advisor && <Alert tone="warning">Montrez cette plante à votre conseiller agricole.</Alert>}
        </div>
      ))}
      {items.length < 10 && (
        <form onSubmit={submit} className="flex flex-col sm:flex-row gap-2">
          <label htmlFor={`q-${diagnosis.alert_id}`} className="sr-only">Votre question</label>
          <input id={`q-${diagnosis.alert_id}`} value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={500}
                 placeholder="Ex. : faut-il recommencer après la pluie ?" className="flex-1 px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:outline-none" />
          <Button type="submit" loading={ask.isPending} disabled={question.trim().length < 5}>Demander</Button>
        </form>
      )}
      {ask.isError && <Alert tone="error">{(ask.error as Error).message}</Alert>}
    </div>
  );
}

/** Résultat d'un diagnostic : couleur de gravité, résumé lu à voix haute, étapes, questions de suivi. */
export function DiagnosisResult({ diagnosis }: { diagnosis: Diagnosis }) {
  const tone = SEVERITY[diagnosis.alert_color as keyof typeof SEVERITY] ?? SEVERITY.orange;
  const healthy = diagnosis.health_status === "Sain";
  return (
    <Card className="space-y-4">
      {diagnosis.is_simulation && <Alert tone="info">Mode démonstration : ce résultat est un exemple, l'IA n'est pas activée sur ce serveur.</Alert>}
      <div className="flex gap-3">
        {diagnosis.alert_id && diagnosis.image_url && <DiagnosisPhoto alertId={diagnosis.alert_id} className="w-24 h-24 rounded border border-neutral-200 shrink-0" />}
        <div className="min-w-0 space-y-1">
          <p className="text-xs text-neutral-500">
            {diagnosis.crop_identified} · {diagnosis.commune}
            {diagnosis.observed_at ? ` · ${formatDate(diagnosis.observed_at)}` : ""}
          </p>
          <h2 className="text-lg font-bold text-neutral-900">{healthy ? "Plante en bonne santé" : diagnosis.disease_name ?? diagnosis.health_status}</h2>
          <div className="flex flex-wrap gap-1.5">
            <Badge tone={healthy ? "green" : diagnosis.alert_color === "red" ? "red" : "amber"}>Gravité : {diagnosis.severity}</Badge>
            <Badge>Certitude : {Math.round(diagnosis.confidence_score * 100)} %</Badge>
          </div>
        </div>
      </div>

      <div className={`p-3.5 rounded-lg border ${tone.box}`}>
        <div className="flex items-start gap-2.5">
          <tone.Icon className={`w-5 h-5 shrink-0 mt-0.5 ${tone.text}`} aria-hidden />
          <p className={`text-base font-semibold ${tone.text}`}>{diagnosis.simple_summary}</p>
        </div>
        {diagnosis.alert_id && (
          <div className="mt-3">
            <AudioButton
              path={{ kind: "diagnosis", id: diagnosis.alert_id }}
              text={`${diagnosis.simple_summary}. ${diagnosis.treatment_steps?.join(". ") || ""}`}
              label="Écouter les conseils"
            />
          </div>
        )}
      </div>

      {!!diagnosis.treatment_steps?.length && (
        <div>
          <h3 className="text-sm font-bold mb-2">Que faire</h3>
          <ol className="space-y-2">
            {diagnosis.treatment_steps.map((s, i) => (
              <li key={i} className="flex gap-3 text-sm">
                <span className="w-6 h-6 rounded-full bg-emerald-800 text-white text-xs font-bold grid place-items-center shrink-0 tabular-nums">{i + 1}</span>
                <span className="pt-0.5">{s}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {!!diagnosis.symptoms?.length && (
        <p className="text-sm text-neutral-700"><span className="font-semibold">Signes observés : </span>{diagnosis.symptoms.join(", ")}</p>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer font-semibold text-emerald-800 min-h-11 flex items-center">Conseil détaillé</summary>
        <p className="text-neutral-700 leading-relaxed">{diagnosis.treatment_advice}</p>
      </details>
      <p className="text-xs text-neutral-500">
        Diagnostic proposé par l'IA, à confirmer par votre conseiller agricole en cas de doute. N'utilisez que des produits homologués.{" "}
        <Link to="/reglementation" className="underline">Voir les fiches pratiques</Link>
      </p>
      {diagnosis.alert_id && <FollowUp diagnosis={diagnosis} />}
    </Card>
  );
}
