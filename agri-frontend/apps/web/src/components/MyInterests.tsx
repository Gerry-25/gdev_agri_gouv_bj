import { api, formatNumber } from "@agri/core";
import { useQuery } from "@tanstack/react-query";
import { MessageCircle } from "lucide-react";
import { unwrap } from "../lib/queries";
import { Badge, Empty, Loading } from "./ui";

/** Offres pour lesquelles l'acheteur a signalé son intérêt. */

export function MyInterests({ limit }: { limit?: number }) {
  const q = useQuery({ queryKey: ["interests", "me"], queryFn: async () => unwrap(await api.GET("/api/v1/market/interests/me")) });
  if (q.isLoading) return <Loading />;
  if (!q.data?.length) return <Empty>Vous n'avez encore signalé d'intérêt pour aucune offre.</Empty>;
  return (
    <ul className="divide-y divide-neutral-100">
      {q.data.slice(0, limit).map((i) => (
        <li key={i.id} className="py-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <span className="font-semibold">{i.offer?.product_name ?? "Offre supprimée"}</span>
            {i.offer && <span className="text-sm text-neutral-600"> · {i.offer.location_commune} · {formatNumber(i.offer.unit_price_fcfa)} FCFA/kg</span>}
            {i.quantity_kg ? <span className="block text-sm text-neutral-600">Vous souhaitez {formatNumber(i.quantity_kg)} kg</span> : null}
          </div>
          {i.offer?.status === "active" ? (
            <a href={i.offer.whatsapp_url} target="_blank" rel="noopener noreferrer" className="min-h-10 px-3 rounded bg-[#25D366] text-white text-sm font-semibold flex items-center gap-1.5"><MessageCircle className="w-4 h-4" aria-hidden /> Relancer</a>
          ) : <Badge>{i.offer?.status === "sold" ? "Vendue" : "Plus disponible"}</Badge>}
        </li>
      ))}
    </ul>
  );
}

