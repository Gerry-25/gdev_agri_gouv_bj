import { api, formatNumber, formatPhone } from "@agri/core";
import { useQuery } from "@tanstack/react-query";
import { MessageCircle } from "lucide-react";
import { type Offer, unwrap } from "../lib/queries";
import { Loading } from "./ui";

/** Acheteurs intéressés par une offre, avec réponse WhatsApp vers leur numéro. */
export function OfferInterests({ offer }: { offer: Offer }) {
  const q = useQuery({
    queryKey: ["interests", offer.id],
    queryFn: async () => unwrap(await api.GET("/api/v1/market/offers/{offer_id}/interests", { params: { path: { offer_id: offer.id } } })),
  });
  if (q.isLoading) return <Loading />;
  return (
    <ul className="space-y-2">
      {(q.data ?? []).map((i) => {
        const digits = (i.buyer_phone ?? "").replace(/\D/g, "");
        const text = encodeURIComponent(`Bonjour, suite à votre intérêt pour mon offre de ${offer.product_name} sur AgriSmart, discutons de la livraison.`);
        return (
          <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span>
              <span className="font-semibold">{i.buyer_name ?? "Acheteur"}</span>
              {i.quantity_kg ? <span className="text-neutral-600"> · {formatNumber(i.quantity_kg)} kg</span> : null}
              {i.buyer_phone && <span className="text-neutral-500 tabular-nums"> · {formatPhone(i.buyer_phone)}</span>}
            </span>
            {digits && (
              <a href={`https://wa.me/${digits}?text=${text}`} target="_blank" rel="noopener noreferrer"
                 className="min-h-9 px-3 bg-[#25D366] text-white rounded font-semibold flex items-center gap-1.5 text-sm">
                <MessageCircle className="w-4 h-4" aria-hidden /> Répondre sur WhatsApp
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}

