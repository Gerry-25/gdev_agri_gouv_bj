import { api } from "@agri/core";
import { useQuery } from "@tanstack/react-query";
import { ImageOff } from "lucide-react";
import { useEffect } from "react";

/** Photo d'un diagnostic : protégée par l'authentification, donc chargée via l'API puis affichée. */
export function DiagnosisPhoto({ alertId, className = "" }: { alertId: string; className?: string }) {
  const q = useQuery({
    queryKey: ["diagnosis-photo", alertId],
    staleTime: Infinity,
    queryFn: async () => {
      const res = await api.GET("/api/v1/monitoring/diagnoses/{alert_id}/image", { params: { path: { alert_id: alertId } }, parseAs: "blob" });
      if (res.error || !res.data) throw new Error();
      return URL.createObjectURL(res.data as unknown as Blob);
    },
  });
  useEffect(() => () => void (q.data && URL.revokeObjectURL(q.data)), [q.data]);
  if (q.isError) return <div className={`grid place-items-center bg-neutral-100 text-neutral-400 ${className}`}><ImageOff className="w-6 h-6" aria-hidden /></div>;
  if (!q.data) return <div className={`bg-neutral-100 animate-pulse ${className}`} />;
  return <img src={q.data} alt="Photo de la plante" className={`object-cover ${className}`} />;
}
