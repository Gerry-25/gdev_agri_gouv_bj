import { api } from "@agri/core";
import { Square, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { buttonClass } from "./ui";

type AudioPath =
  | { kind: "diagnosis"; id: string }
  | { kind: "fertilization"; landId: string }
  | { kind: "assistant"; id: string }
  | { kind: "guide"; slug: string };

async function fetchAudio(p: AudioPath): Promise<Blob> {
  const opts = { parseAs: "blob" as const };
  const res =
    p.kind === "diagnosis" ? await api.GET("/api/v1/monitoring/diagnoses/{alert_id}/audio", { params: { path: { alert_id: p.id } }, ...opts })
    : p.kind === "fertilization" ? await api.GET("/api/v1/lands/{land_id}/fertilization-plans/latest/audio", { params: { path: { land_id: p.landId } }, ...opts })
    : p.kind === "assistant" ? await api.GET("/api/v1/assistant/answers/{answer_id}/audio", { params: { path: { answer_id: p.id } }, ...opts })
    : await api.GET("/api/v1/knowledge/guides/{slug}/audio", { params: { path: { slug: p.slug } }, ...opts });
  if (res.error || !res.data) throw new Error("Lecture audio indisponible.");
  return res.data as unknown as Blob;
}

/** Lecture audio (générée par le serveur, gardée en cache) : pour les exploitants qui lisent difficilement. */
export function AudioButton({ path, label = "Écouter" }: { path: AudioPath; label?: string }) {
  const [state, setState] = useState<"idle" | "loading" | "playing" | "error">("idle");
  const audio = useRef<HTMLAudioElement | null>(null);
  useEffect(() => () => audio.current?.pause(), []);

  const toggle = async () => {
    if (state === "playing") {
      audio.current?.pause();
      return setState("idle");
    }
    setState("loading");
    try {
      const url = URL.createObjectURL(await fetchAudio(path));
      audio.current = new Audio(url);
      audio.current.onended = () => setState("idle");
      await audio.current.play();
      setState("playing");
    } catch {
      setState("error");
    }
  };
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button type="button" onClick={toggle} disabled={state === "loading"} aria-busy={state === "loading" || undefined} className={buttonClass("soft", "min-h-11")}>
        {state === "playing" ? <Square className="w-4 h-4" aria-hidden /> : <Volume2 className="w-4 h-4" aria-hidden />}
        {state === "loading" ? "Préparation…" : state === "playing" ? "Arrêter" : label}
      </button>
      {state === "error" && <span className="text-xs text-red-700">Audio indisponible pour le moment.</span>}
    </span>
  );
}
