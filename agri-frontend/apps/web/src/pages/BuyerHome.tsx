import { api, formatNumber, useSession } from "@agri/core";
import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, Heart, ShoppingBasket, Tags } from "lucide-react";
import { Link } from "react-router-dom";
import { buttonClass, Card, CardHeader, CardLink, Loading, Metric } from "../components/ui";
import { unwrap } from "../lib/queries";
import { MyInterests } from "../components/MyInterests";

/** Portail acheteur : offres disponibles, offres suivies, repères de prix. */
export function BuyerHome() {
  const { user } = useSession();
  const offers = useQuery({ queryKey: ["market", "catalogue", "home"], queryFn: async () => unwrap(await api.GET("/api/v1/market/offers", { params: { query: { limit: 100 } } })) });
  const interests = useQuery({ queryKey: ["interests", "me"], queryFn: async () => unwrap(await api.GET("/api/v1/market/interests/me")) });
  const list = offers.data ?? [];
  const volumeT = list.reduce((s, o) => s + o.quantity_kg, 0) / 1000;
  const verified = list.filter((o) => o.origin_verified).length;
  const latest = list.slice(0, 4);
  return (
    <div className="space-y-5 sm:space-y-6">
      <Card>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <p className="text-xs font-bold text-emerald-800">Portail acheteur</p>
            <h1 className="text-xl font-bold tracking-tight">{user?.full_name}</h1>
            <p className="text-sm text-neutral-600">Achetez directement aux producteurs, avec l'origine des récoltes.</p>
          </div>
          <Link to="/marche" className={buttonClass("primary")}><ShoppingBasket className="w-4 h-4" aria-hidden /> Voir le catalogue</Link>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-5 pt-5 border-t border-neutral-100">
          <Metric label="Offres disponibles" value={offers.isLoading ? "…" : list.length} />
          <Metric label="Volume offert" value={formatNumber(volumeT, 1)} unit="t" />
          <Metric label="Issues de parcelles vérifiées" value={verified} hint={list.length ? `${Math.round((100 * verified) / list.length)} % des offres` : undefined} hintTone="green" />
          <Metric label="Offres suivies" value={interests.data?.length ?? "…"} />
        </div>
      </Card>
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <Card className="lg:col-span-7">
          <CardHeader icon={ShoppingBasket} title="Dernières offres" action={<CardLink to="/marche">Tout voir</CardLink>} />
          {offers.isLoading && <Loading />}
          <ul className="divide-y divide-neutral-100">
            {latest.map((o) => (
              <li key={o.id} className="py-3 flex flex-wrap items-center justify-between gap-2">
                <span>
                  <span className="font-semibold">{o.product_name}</span>
                  <span className="text-sm text-neutral-600"> · {o.location_commune} · {formatNumber(o.quantity_kg / 1000, 1)} t</span>
                  {o.origin_verified && <BadgeCheck className="inline w-4 h-4 text-emerald-700 ml-1" aria-label="Parcelle vérifiée" />}
                </span>
                <span className="font-bold text-emerald-900 tabular-nums">{formatNumber(o.unit_price_fcfa)} FCFA/kg</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="lg:col-span-5">
          <CardHeader icon={Heart} title="Mes offres suivies" />
          <MyInterests limit={5} />
        </Card>
      </div>
      <Link to="/marche" className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-800 hover:underline"><Tags className="w-4 h-4" aria-hidden /> Consulter les prix de référence</Link>
    </div>
  );
}
