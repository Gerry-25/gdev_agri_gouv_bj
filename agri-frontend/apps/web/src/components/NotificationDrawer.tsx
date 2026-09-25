import { api, formatRelative } from "@agri/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, X } from "lucide-react";
import { useEffect } from "react";
import { Pictogram } from "../lib/pictograms";
import { unwrap } from "../lib/queries";
import { Loading } from "./ui";

export function NotificationDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["notifications", "list"],
    enabled: open,
    queryFn: async () => unwrap(await api.GET("/api/v1/notifications/me", { params: { query: { limit: 50 } } })),
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["notifications"] });
  const markOne = useMutation({
    mutationFn: (id: string) => api.PATCH("/api/v1/notifications/{notification_id}/read", { params: { path: { notification_id: id } } }),
    onSuccess: refresh,
  });
  const markAll = useMutation({ mutationFn: () => api.POST("/api/v1/notifications/me/read-all"), onSuccess: refresh });

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const items = list.data ?? [];
  const unread = items.filter((n) => !n.read).length;
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-labelledby="notif-title">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="absolute inset-y-0 right-0 max-w-md w-full bg-white shadow-2xl border-l border-neutral-200 flex flex-col">
        <div className="px-5 py-4 border-b border-neutral-200 flex items-center justify-between">
          <h2 id="notif-title" className="text-base font-bold text-neutral-900 flex items-center gap-2">
            <Bell className="w-5 h-5 text-emerald-800" aria-hidden /> Notifications
          </h2>
          <button type="button" onClick={onClose} className="p-2 text-neutral-500 hover:text-neutral-800 rounded cursor-pointer" aria-label="Fermer">
            <X className="w-5 h-5" />
          </button>
        </div>
        {unread > 0 && (
          <div className="px-5 py-2 bg-neutral-50 border-b border-neutral-100 flex items-center justify-between text-sm text-neutral-600">
            <span>{unread} non lue{unread > 1 ? "s" : ""}</span>
            <button type="button" onClick={() => markAll.mutate()} className="text-emerald-800 font-semibold hover:underline cursor-pointer">
              Tout marquer comme lu
            </button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto divide-y divide-neutral-100">
          {list.isLoading && <Loading />}
          {items.map((n) => (
            <button type="button"
              key={n.id}
              onClick={() => !n.read && markOne.mutate(n.id)}
              className={`w-full text-left p-4 space-y-1 cursor-pointer ${n.read ? "bg-white hover:bg-neutral-50" : "bg-emerald-50/40 hover:bg-emerald-50"}`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="flex items-center gap-2 text-sm font-semibold text-neutral-900">
                  <Pictogram code={n.pictogram} /> {n.title}
                </span>
                <span className="text-xs text-neutral-500 shrink-0">{formatRelative(n.created_at)}</span>
              </div>
              <p className="text-sm text-neutral-600 pl-6 leading-relaxed">{n.message}</p>
            </button>
          ))}
          {list.isSuccess && items.length === 0 && <p className="p-12 text-center text-sm text-neutral-500">Aucune notification pour le moment.</p>}
        </div>
      </div>
    </div>
  );
}
