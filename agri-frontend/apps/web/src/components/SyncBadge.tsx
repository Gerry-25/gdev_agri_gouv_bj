import { db } from "@agri/core";
import { useLiveQuery } from "dexie-react-hooks";
import { CloudOff, RefreshCw, TriangleAlert, Wifi } from "lucide-react";
import { Link } from "react-router-dom";
import { useOnline } from "../lib/useOnline";

/** Remplace le faux bouton « hors ligne » du template par l'état réel du réseau et de la file d'envoi. */
export function SyncBadge() {
  const online = useOnline();
  const pending = useLiveQuery(() => db.outbox.where("status").equals("pending").count(), [], 0);
  const failed = useLiveQuery(() => db.outbox.where("status").equals("failed").count(), [], 0);
  const base = "px-2.5 min-h-9 text-xs font-semibold rounded border flex items-center gap-1.5 whitespace-nowrap";

  if (failed) {
    return (
      <Link to="/envois" className={`${base} bg-red-50 border-red-300 text-red-800`}>
        <TriangleAlert className="w-4 h-4" aria-hidden /> {failed} refusé{failed > 1 ? "s" : ""}
      </Link>
    );
  }
  if (!online) {
    return (
      <Link to="/envois" className={`${base} bg-amber-50 border-amber-300 text-amber-900`}>
        <CloudOff className="w-4 h-4" aria-hidden /> Hors ligne{pending ? ` (${pending})` : ""}
      </Link>
    );
  }
  if (pending) {
    return (
      <Link to="/envois" className={`${base} bg-neutral-50 border-neutral-200 text-neutral-700`}>
        <RefreshCw className="w-4 h-4 text-emerald-700" aria-hidden /> {pending} en attente
      </Link>
    );
  }
  return (
    <span className={`${base} bg-neutral-50 border-neutral-200 text-neutral-700 hidden sm:flex`} title="Connecté">
      <Wifi className="w-4 h-4 text-emerald-700" aria-hidden /> En ligne
    </span>
  );
}
