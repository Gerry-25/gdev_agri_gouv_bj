import { api, formatNumber, useSession } from "@agri/core";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowRight, Award, CheckCircle2, Clock, HeartPulse, Landmark, MapPin, Plus, ShoppingBag, Sparkles, Sprout, Warehouse, XCircle,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, buttonClass, Card, CardHeader, CardLink, Empty, Loading, Metric } from "../components/ui";
import { OfferInterests as Interests } from "../components/OfferInterests";
import { WeatherWidget } from "../components/WeatherWidget";
import { type Land, type Offer, unwrap, useMyLands, useMyOffers, useMyPerformance } from "../lib/queries";

function LandStatus({ land }: { land: Land }) {
  if (land.dispute_flag) return <Badge tone="red"><AlertTriangle className="w-3.5 h-3.5" aria-hidden /> Litige en cours</Badge>;
  if (land.verification_status === "verifiee") return <Badge tone="green"><CheckCircle2 className="w-3.5 h-3.5" aria-hidden /> Vérifiée par un agent</Badge>;
  if (land.verification_status === "rejetee") return <Badge tone="red"><XCircle className="w-3.5 h-3.5" aria-hidden /> Non validée</Badge>;
  return <Badge tone="amber"><Clock className="w-3.5 h-3.5" aria-hidden /> En attente de vérification</Badge>;
}

function LandCard({ land }: { land: Land }) {
  const harvests = useQuery({
    queryKey: ["harvests", land.id],
    queryFn: async () => unwrap(await api.GET("/api/v1/lands/{land_id}/harvests", { params: { path: { land_id: land.id } } })),
  });
  const last = harvests.data?.[0];
  const border = land.dispute_flag ? "border-red-300 bg-red-50/30" : land.verification_status === "verifiee" ? "border-neutral-200" : "border-amber-200 bg-amber-50/30";
  return (
    <Link to={`/cadastre/${land.id}`} className={`block p-3.5 rounded-lg border hover:border-emerald-700 transition-colors ${border}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-neutral-900">{land.crop_type}{land.locality ? ` · ${land.locality}` : ""}</h3>
          <p className="text-xs text-neutral-500 tabular-nums">{land.cadastral_reference ?? `Parcelle ${land.id.slice(-6).toUpperCase()}`}</p>
        </div>
        <LandStatus land={land} />
      </div>
      <div className="flex flex-wrap items-center gap-x-2 text-sm text-neutral-600 mt-2">
        <span className="font-bold text-neutral-900 tabular-nums">{formatNumber(land.surface_hectares, 2)} ha</span>
        <span aria-hidden>·</span>
        <span>{land.commune}</span>
      </div>
      <div className="mt-2 pt-2 border-t border-neutral-100 flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="text-neutral-600">
          Récolte prévue : <span className="font-semibold text-neutral-900 tabular-nums">{formatNumber(land.estimated_yield_kg / 1000, 1)} t</span>
        </span>
        {last ? (
          <span className="text-emerald-800 font-semibold">
            Récolte {last.season} : <span className="tabular-nums">{formatNumber(last.actual_yield_kg / 1000, 1)} t</span>
          </span>
        ) : (
          <span className="text-amber-800">Aucune récolte déclarée</span>
        )}
      </div>
    </Link>
  );
}

const OFFER_STATUS = { active: ["Disponible", "green"], sold: ["Vendue", "blue"], withdrawn: ["Retirée", "neutral"] } as const;

function OfferCard({ offer }: { offer: Offer }) {
  const [open, setOpen] = useState(false);
  const [label, tone] = OFFER_STATUS[offer.status];
  const interested = offer.interest_count ?? 0;
  return (
    <div className="p-4 bg-neutral-50 border border-neutral-200 rounded-lg space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="text-sm font-bold text-neutral-900">{offer.product_name}</span>
          <div className="text-xs text-neutral-500">{offer.location_commune}</div>
        </div>
        <Badge tone={tone}>{label}</Badge>
      </div>
      <div className="flex items-baseline justify-between text-sm pt-2 border-t border-neutral-200/70">
        <span className="text-neutral-600">Volume : <span className="font-bold text-neutral-900 tabular-nums">{formatNumber(offer.quantity_kg / 1000, 1)} t</span></span>
        <span className="font-bold text-emerald-900 tabular-nums">{formatNumber(offer.unit_price_fcfa)} FCFA/kg</span>
      </div>
      {interested > 0 && offer.status === "active" && (
        <div className="p-2.5 bg-blue-50 border border-blue-200 rounded text-sm text-blue-950 space-y-2">
          <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="w-full flex items-center justify-between gap-2 font-semibold cursor-pointer">
            <span>{interested} acheteur{interested > 1 ? "s" : ""} intéressé{interested > 1 ? "s" : ""}</span>
            <span className="text-blue-800 underline">{open ? "Masquer" : "Voir"}</span>
          </button>
          {open && <Interests offer={offer} />}
        </div>
      )}
    </div>
  );
}

export function FarmerDashboard() {
  const { user } = useSession();
  const lands = useMyLands();
  const offers = useMyOffers();
  const perf = useMyPerformance();
  const openCalls = useQuery({
    queryKey: ["calls", "open"],
    queryFn: async () => unwrap(await api.GET("/api/v1/calls", { params: { query: { phase: "ouvert" } } })),
  });
  const stocks = useQuery({
    queryKey: ["stocks", "me"],
    queryFn: async () => unwrap(await api.GET("/api/v1/storage/lots/me")) as unknown as { risk?: { level?: string } | null }[],
  });

  const myLands = lands.data ?? [];
  const myOffers = offers.data ?? [];
  const totalHa = myLands.reduce((s, l) => s + l.surface_hectares, 0);
  const forecastT = myLands.reduce((s, l) => s + l.estimated_yield_kg, 0) / 1000;
  const verified = myLands.filter((l) => l.verification_status === "verifiee").length;
  const crops = [...new Set(myLands.map((l) => l.crop_type))];
  const active = myOffers.filter((o) => o.status === "active");
  const interested = active.reduce((s, o) => s + (o.interest_count ?? 0), 0);
  const commune = user?.commune ?? myLands[0]?.commune;
  const riskyStocks = (stocks.data ?? []).filter((s) => s.risk?.level === "eleve").length;

  return (
    <div className="space-y-5 sm:space-y-6">
      <Card>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-12 h-12 rounded-lg bg-emerald-100 border border-emerald-200 flex items-center justify-center shrink-0">
              <Sprout className="w-6 h-6 text-emerald-800" aria-hidden />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-bold text-emerald-800">Mon exploitation</p>
              <h1 className="text-xl font-bold tracking-tight text-neutral-900">{user?.full_name}</h1>
              <p className="text-sm text-neutral-600 mt-0.5">
                {commune ? `Commune de ${commune}` : "Commune non renseignée"} · Campagne {new Date().getFullYear()}
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 md:flex gap-2">
            <Link to="/diagnostic" className={buttonClass("soft")}>
              <Sparkles className="w-4 h-4 text-emerald-800" aria-hidden /> Diagnostic IA
            </Link>
            <Link to="/cadastre/nouvelle" className={buttonClass("primary")}>
              <Plus className="w-4 h-4" aria-hidden /> Nouvelle parcelle
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-5 pt-5 border-t border-neutral-100">
          <Metric label="Parcelles enregistrées" value={myLands.length} unit={`(${formatNumber(totalHa, 1)} ha)`}
                  hint={`${verified} vérifiée${verified > 1 ? "s" : ""} par un agent`} hintTone="green" />
          <Metric label="Score de performance" value={perf.data ? formatNumber(perf.data.score, 0) : "…"} unit="/ 100"
                  hint={perf.data ? (perf.data.eligible ? "Éligible aux terres de l'État" : "Pas encore éligible") : undefined}
                  hintTone={perf.data?.eligible ? "green" : "amber"} />
          <Metric label="Récolte prévue" value={formatNumber(forecastT, 1)} unit="t" hint={crops.join(", ") || undefined} />
          <Metric label="Annonces actives" value={active.length} hint={interested ? `${interested} acheteur${interested > 1 ? "s" : ""} intéressé${interested > 1 ? "s" : ""}` : undefined} hintTone="blue" />
        </div>
      </Card>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        <Link to="/sante" className="p-3.5 rounded-lg border border-red-200 bg-red-50 text-red-950 flex items-center gap-3 hover:border-red-400 transition-colors">
          <HeartPulse className="w-5 h-5 text-red-600 shrink-0" aria-hidden />
          <span className="text-sm flex-1">
            <span className="font-bold">Santé & Urgences</span> : premiers secours IA et assistance médicale
          </span>
          <ArrowRight className="w-4 h-4 text-red-600" aria-hidden />
        </Link>
        {!!openCalls.data?.length && (
          <Link to="/concessions" className="p-3.5 rounded-lg border border-purple-200 bg-purple-50 text-purple-950 flex items-center gap-3 hover:border-purple-400">
            <Landmark className="w-5 h-5 text-purple-700 shrink-0" aria-hidden />
            <span className="text-sm flex-1">
              <span className="font-bold">{openCalls.data.length} terre{openCalls.data.length > 1 ? "s" : ""} de l'État</span> ouverte{openCalls.data.length > 1 ? "s" : ""} aux candidatures
            </span>
            <ArrowRight className="w-4 h-4" aria-hidden />
          </Link>
        )}
        {riskyStocks > 0 && (
          <Link to="/stockage" className="p-3.5 rounded-lg border border-amber-300 bg-amber-50 text-amber-950 flex items-center gap-3 hover:border-amber-500">
            <Warehouse className="w-5 h-5 text-amber-700 shrink-0" aria-hidden />
            <span className="text-sm flex-1">
              <span className="font-bold">{riskyStocks} stock{riskyStocks > 1 ? "s" : ""} à risque</span> de pertes : voir les conseils
            </span>
            <ArrowRight className="w-4 h-4" aria-hidden />
          </Link>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 sm:gap-6">
        <Card className="lg:col-span-7">
          <CardHeader icon={MapPin} title={`Mes parcelles (${myLands.length})`} action={<CardLink to="/cadastre">Voir la carte</CardLink>} />
          {lands.isLoading && <Loading />}
          {lands.isSuccess && myLands.length === 0 && (
            <Empty>
              Aucune parcelle enregistrée. <Link to="/cadastre/nouvelle" className="text-emerald-800 font-semibold underline">Tracer ma première parcelle</Link>
            </Empty>
          )}
          <div className="space-y-3">
            {myLands.map((l) => <LandCard key={l.id} land={l} />)}
          </div>
        </Card>

        <Card className="lg:col-span-5">
          <CardHeader icon={Award} title={`Mon score (${perf.data ? formatNumber(perf.data.score, 0) : "…"} / 100)`}
                      action={perf.data && <Badge tone={perf.data.eligible ? "green" : "amber"}>{perf.data.eligible ? "Éligible" : "Non éligible"}</Badge>} />
          <p className="text-sm text-neutral-600 leading-relaxed mb-3">
            Ce score compte pour l'attribution des terres de l'État. Seules les récoltes sur des parcelles vérifiées sont prises en compte.
          </p>
          {perf.isLoading && <Loading />}
          {perf.data && !perf.data.eligible && (
            <ul className="mb-3 p-3 rounded border border-amber-200 bg-amber-50 text-sm text-amber-950 space-y-1 list-disc pl-5">
              {perf.data.ineligibility_reasons.map((r) => <li key={r}>{r}</li>)}
            </ul>
          )}
          <ul className="space-y-2.5">
            {perf.data?.components.map((c) => (
              <li key={c.key} className="p-3 bg-neutral-50 border border-neutral-200 rounded space-y-1.5">
                <div className="flex items-start justify-between gap-3 text-sm">
                  <span className="font-semibold text-neutral-900">{c.label}</span>
                  <span className="font-bold tabular-nums text-emerald-900 shrink-0">{formatNumber(c.score, 0)} / 100</span>
                </div>
                <div className="h-1.5 bg-neutral-200 rounded" aria-hidden>
                  <div className="h-1.5 bg-emerald-700 rounded" style={{ width: `${Math.min(100, c.score)}%` }} />
                </div>
                <p className="text-xs text-neutral-600">
                  {c.detail} · compte pour {Math.round(c.weight * 100)} % du score
                </p>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card>
        <CardHeader icon={ShoppingBag} title="Mes annonces" action={<CardLink to="/marche">Voir le marché</CardLink>} />
        {offers.isLoading && <Loading />}
        {offers.isSuccess && myOffers.length === 0 && (
          <Empty>
            Aucune annonce. <Link to="/marche" className="text-emerald-800 font-semibold underline">Publier une récolte</Link>
          </Empty>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {myOffers.slice(0, 6).map((o) => <OfferCard key={o.id} offer={o} />)}
        </div>
      </Card>

      <WeatherWidget landId={myLands[0]?.id} commune={commune} />
    </div>
  );
}
