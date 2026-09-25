import { api, apiErrorMessage, enqueue, formatNumber, newClientRef, useSession } from "@agri/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Camera, CloudOff, Heart, MapPin, MessageCircle, Phone, Plus, ShoppingBasket, Sparkles, Tags } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { MyInterests } from "../../components/MyInterests";
import { OfferInterests } from "../../components/OfferInterests";
import { Alert, Badge, Button, Card, CardHeader, Empty, Loading } from "../../components/ui";
import { COMMON_CROPS, DEPARTMENTS } from "../../lib/benin";
import { compressImage } from "../../lib/image";
import { type Offer, unwrap, useMyLands, useMyOffers } from "../../lib/queries";

const inputCls = "w-full px-3 py-2.5 text-base border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";

function Field({ id, label, children, hint }: { id: string; label: string; children: ReactNode; hint?: ReactNode }) {
  return <div><label htmlFor={id} className="block text-sm font-semibold mb-1">{label}</label>{children}{hint && <div className="text-xs text-neutral-500 mt-1">{hint}</div>}</div>;
}

function useDebounced<T>(value: T, ms = 500) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

// --- Catalogue -------------------------------------------------------------------------

function InterestForm({ offer, onDone }: { offer: Offer; onDone: () => void }) {
  const qc = useQueryClient();
  const [qty, setQty] = useState("");
  const [message, setMessage] = useState("");
  const send = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/market/offers/{offer_id}/interest", {
      params: { path: { offer_id: offer.id } }, body: { quantity_kg: qty ? Number(qty) : undefined, message: message || undefined },
    })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["market"] }); qc.invalidateQueries({ queryKey: ["interests"] }); onDone(); },
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); send.mutate(); }} className="space-y-2 p-3 rounded border border-blue-200 bg-blue-50/50">
      <Field id={`iq-${offer.id}`} label="Quantité souhaitée (kg, facultatif)"><input id={`iq-${offer.id}`} inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value.replace(/\D/g, ""))} className={inputCls} /></Field>
      <Field id={`im-${offer.id}`} label="Message au producteur (facultatif)"><input id={`im-${offer.id}`} value={message} maxLength={500} onChange={(e) => setMessage(e.target.value)} className={inputCls} placeholder="Ex. : livraison possible à Cotonou ?" /></Field>
      <Button type="submit" className="w-full" loading={send.isPending}>Prévenir le producteur</Button>
      {send.isError && <Alert tone="error">{(send.error as Error).message}</Alert>}
    </form>
  );
}

function CatalogueCard({ offer, mine }: { offer: Offer; mine: boolean }) {
  const [interest, setInterest] = useState(false);
  const [sent, setSent] = useState(false);
  return (
    <li className="p-4 bg-white border border-neutral-200 rounded-lg flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-bold text-neutral-900">{offer.product_name}</h3>
          <p className="text-sm text-neutral-600 flex items-center gap-1"><MapPin className="w-3.5 h-3.5" aria-hidden /> {offer.location_commune}{offer.department ? ` (${offer.department})` : ""}</p>
        </div>
        {offer.origin_verified && <Badge tone="green"><BadgeCheck className="w-3.5 h-3.5" aria-hidden /> Parcelle vérifiée</Badge>}
      </div>
      {offer.description && <p className="text-sm text-neutral-700 leading-relaxed">{offer.description}</p>}
      <div className="flex items-baseline justify-between text-sm pt-2 border-t border-neutral-100">
        <span>Disponible : <strong className="tabular-nums">{formatNumber(offer.quantity_kg / 1000, 1)} t</strong></span>
        <span className="text-lg font-bold text-emerald-900 tabular-nums">{formatNumber(offer.unit_price_fcfa)} FCFA/kg</span>
      </div>
      {mine ? (
        <p className="text-xs text-neutral-500">C'est votre annonce.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2">
            <a href={offer.tel_url} className="min-h-11 rounded border border-neutral-300 font-semibold text-sm flex items-center justify-center gap-1.5 hover:bg-neutral-50"><Phone className="w-4 h-4" aria-hidden /> Appeler</a>
            <a href={offer.whatsapp_url} target="_blank" rel="noopener noreferrer" className="min-h-11 rounded bg-[#25D366] text-white font-semibold text-sm flex items-center justify-center gap-1.5"><MessageCircle className="w-4 h-4" aria-hidden /> WhatsApp</a>
          </div>
          {sent ? <Alert tone="success">Le producteur a été prévenu de votre intérêt.</Alert> : interest ? <InterestForm offer={offer} onDone={() => setSent(true)} /> : (
            <Button variant="outline" onClick={() => setInterest(true)}><Heart className="w-4 h-4" aria-hidden /> Je suis intéressé</Button>
          )}
        </>
      )}
    </li>
  );
}

function Catalogue() {
  const { user } = useSession();
  const [f, setF] = useState({ product: "", department: "", max_price: "", verified: false });
  const product = useDebounced(f.product);
  const q = useQuery({
    queryKey: ["market", "catalogue", product, f.department, f.max_price, f.verified],
    queryFn: async () => unwrap(await api.GET("/api/v1/market/offers", { params: { query: {
      product: product || undefined, department: f.department || undefined, max_price: f.max_price ? Number(f.max_price) : undefined,
      verified_origin: f.verified || undefined, limit: 60,
    } } })),
  });
  return (
    <div className="space-y-4">
      <Card>
        <div className="grid gap-3 sm:grid-cols-4 items-end">
          <Field id="fp" label="Produit"><input id="fp" list="mcrops" value={f.product} onChange={(e) => setF({ ...f, product: e.target.value })} className={inputCls} placeholder="Tous" /><datalist id="mcrops">{COMMON_CROPS.map((c) => <option key={c} value={c} />)}</datalist></Field>
          <Field id="fd" label="Département"><select id="fd" value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })} className={inputCls}><option value="">Tous</option>{DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}</select></Field>
          <Field id="fm" label="Prix maximum (FCFA/kg)"><input id="fm" inputMode="numeric" value={f.max_price} onChange={(e) => setF({ ...f, max_price: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <label className="flex items-center gap-2 min-h-11 text-sm"><input type="checkbox" className="w-5 h-5 accent-emerald-800" checked={f.verified} onChange={(e) => setF({ ...f, verified: e.target.checked })} /> Parcelles vérifiées uniquement</label>
        </div>
      </Card>
      {q.isLoading && <Loading />}
      {q.isSuccess && !q.data.length && <Empty>Aucune offre ne correspond à ces critères.</Empty>}
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {q.data?.map((o) => <CatalogueCard key={o.id} offer={o} mine={o.farmer_npi === user?.npi} />)}
      </ul>
    </div>
  );
}

// --- Prix de référence ------------------------------------------------------------------

interface PriceRow { product: string; department: string | null; sold: { avg: number; min: number; max: number; count: number } | null; offered: { avg: number; min: number; max: number; count: number } | null }

function Prices() {
  const [product, setProduct] = useState("");
  const [department, setDepartment] = useState("");
  const p = useDebounced(product);
  const q = useQuery({
    queryKey: ["market", "prices", p, department],
    queryFn: async () => unwrap(await api.GET("/api/v1/market/prices", { params: { query: { product: p || undefined, department: department || undefined, days: 90 } } })) as unknown as { prices: PriceRow[] },
  });
  const cell = (v: PriceRow["sold"]) => v ? <><span className="font-semibold tabular-nums">{formatNumber(v.avg)}</span><span className="block text-xs text-neutral-500 tabular-nums">{formatNumber(v.min)} à {formatNumber(v.max)} · {v.count} obs.</span></> : <span className="text-neutral-400">—</span>;
  return (
    <Card>
      <CardHeader icon={Tags} title="Prix constatés sur 90 jours (FCFA/kg)" />
      <div className="grid gap-3 sm:grid-cols-2 mb-4">
        <Field id="pp" label="Produit"><input id="pp" list="mcrops2" value={product} onChange={(e) => setProduct(e.target.value)} className={inputCls} placeholder="Tous" /><datalist id="mcrops2">{COMMON_CROPS.map((c) => <option key={c} value={c} />)}</datalist></Field>
        <Field id="pd" label="Département"><select id="pd" value={department} onChange={(e) => setDepartment(e.target.value)} className={inputCls}><option value="">Tous</option>{DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}</select></Field>
      </div>
      {q.isLoading && <Loading />}
      {q.data && !q.data.prices.length && <Empty>Pas encore assez de données.</Empty>}
      {!!q.data?.prices.length && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-neutral-500 border-b border-neutral-200"><th className="py-2 pr-3 font-semibold">Produit</th><th className="py-2 pr-3 font-semibold">Département</th><th className="py-2 pr-3 font-semibold">Prix de vente constaté</th><th className="py-2 font-semibold">Prix demandé</th></tr></thead>
            <tbody>{q.data.prices.map((r, i) => (
              <tr key={i} className="border-b border-neutral-100 align-top">
                <td className="py-2 pr-3 capitalize font-semibold">{r.product}</td><td className="py-2 pr-3">{r.department ?? "—"}</td><td className="py-2 pr-3">{cell(r.sold)}</td><td className="py-2">{cell(r.offered)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-neutral-500 mt-3">Calculés à partir des annonces et des ventes déclarées sur AgriSmart : ce sont des repères, pas des prix officiels.</p>
    </Card>
  );
}

// --- Publier une annonce (avec aide de l'IA) ------------------------------------------------

interface Suggestion { scope: string | null; basis: string; observations: number; suggested_min_fcfa_kg?: number; suggested_max_fcfa_kg?: number; reference_avg_fcfa_kg?: number }

function PublishForm({ onDone }: { onDone: () => void }) {
  const { user } = useSession();
  const qc = useQueryClient();
  const lands = useMyLands();
  const [f, setF] = useState({ product_name: "", quantity_kg: "", unit_price_fcfa: "", contact_phone: user?.phone ?? "", land_id: "", location_commune: user?.commune ?? "", department: user?.department ?? "", description: "" });
  const [notes, setNotes] = useState("");
  const [photo, setPhoto] = useState<Blob | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [queued, setQueued] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const land = lands.data?.find((l) => l.id === f.land_id);
  const product = useDebounced(f.product_name.split(" ")[0]);
  const dept = land?.department ?? f.department;

  const suggestion = useQuery({
    queryKey: ["market", "suggestion", product, dept],
    enabled: product.length >= 2,
    queryFn: async () => unwrap(await api.GET("/api/v1/market/price-suggestion", { params: { query: { product, department: dept || undefined } } })) as unknown as Suggestion,
  });
  const draft = useMutation({
    mutationFn: async () => {
      const form = new FormData();
      form.append("notes", notes);
      if (f.quantity_kg) form.append("quantity_kg", f.quantity_kg);
      if (dept) form.append("department", dept);
      if (photo) form.append("file", photo, "photo.jpg");
      const { data, error: err } = await api.POST("/api/v1/market/offers/ai-draft", { body: form as never });
      if (err) throw new Error(apiErrorMessage(err));
      return data as unknown as { product_name: string; quality_description: string; listing_text: string; quality_warnings: string[] };
    },
    onSuccess: (d) => {
      setF((prev) => ({ ...prev, product_name: d.product_name, description: `${d.listing_text} ${d.quality_description}`.trim().slice(0, 800) }));
      setWarnings(d.quality_warnings);
    },
  });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const body = {
      product_name: f.product_name, quantity_kg: Number(f.quantity_kg), unit_price_fcfa: Number(f.unit_price_fcfa), contact_phone: f.contact_phone,
      land_id: f.land_id || undefined, location_commune: f.land_id ? undefined : f.location_commune, department: f.land_id ? undefined : f.department || undefined,
      description: f.description || undefined, client_ref: newClientRef(),
    };
    try {
      const { error: err } = await api.POST("/api/v1/market/offers", { body: body as never });
      if (err) return setError(apiErrorMessage(err));
      qc.invalidateQueries({ queryKey: ["offers"] });
      qc.invalidateQueries({ queryKey: ["market"] });
      onDone();
    } catch {
      await enqueue("offer", `Annonce ${f.product_name} (${f.quantity_kg} kg)`, body);
      setQueued(true);
    } finally {
      setBusy(false);
    }
  };
  if (queued) return <Card><Alert tone="warning"><span className="flex gap-2"><CloudOff className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />Annonce gardée sur le téléphone : elle sera publiée au retour du réseau.</span></Alert></Card>;

  const s = suggestion.data;
  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <Card className="space-y-3">
        <CardHeader icon={Sparkles} title="Rédiger avec l'aide de l'IA (facultatif)" />
        <p className="text-sm text-neutral-600">Quelques mots et une photo de la récolte suffisent : l'IA propose un titre et une description honnête.</p>
        <Field id="notes" label="En quelques mots"><input id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} className={inputCls} placeholder="Ex. : maïs blanc bien sec, récolte d'août, en sacs" /></Field>
        <div className="flex flex-wrap items-center gap-2">
          <label className="min-h-11 px-4 rounded border border-neutral-300 text-sm font-semibold flex items-center gap-2 cursor-pointer hover:bg-neutral-50 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-emerald-700">
            <Camera className="w-4 h-4" aria-hidden /> {photo ? "Photo ajoutée" : "Ajouter une photo"}
            <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={async (e) => { const file = e.target.files?.[0]; if (file) setPhoto(await compressImage(file, 1024)); }} />
          </label>
          <Button variant="soft" onClick={() => draft.mutate()} loading={draft.isPending} disabled={notes.trim().length < 3}><Sparkles className="w-4 h-4" aria-hidden /> Proposer l'annonce</Button>
        </div>
        {draft.isError && <Alert tone="error">{(draft.error as Error).message}</Alert>}
        {warnings.map((w) => <Alert key={w} tone="warning">{w}</Alert>)}
      </Card>

      <Card className="space-y-4">
        <CardHeader icon={ShoppingBasket} title="Mon annonce" />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field id="op" label="Produit"><input id="op" list="mcrops3" value={f.product_name} onChange={set("product_name")} className={inputCls} /><datalist id="mcrops3">{COMMON_CROPS.map((c) => <option key={c} value={c} />)}</datalist></Field>
          <Field id="oq" label="Quantité disponible (kg)"><input id="oq" inputMode="numeric" value={f.quantity_kg} onChange={(e) => setF({ ...f, quantity_kg: e.target.value.replace(/\D/g, "") })} className={`${inputCls} tabular-nums`} /></Field>
          <Field id="ou" label="Prix (FCFA par kg)" hint={s?.reference_avg_fcfa_kg ? (
            <span>Prix conseillé : <strong className="tabular-nums">{formatNumber(s.suggested_min_fcfa_kg!)} à {formatNumber(s.suggested_max_fcfa_kg!)}</strong> ({s.basis}, {s.observations} obs.){" "}
              <button type="button" className="underline text-emerald-800 font-semibold" onClick={() => setF({ ...f, unit_price_fcfa: String(s.reference_avg_fcfa_kg) })}>Utiliser {formatNumber(s.reference_avg_fcfa_kg)}</button></span>
          ) : product.length >= 2 && s ? "Pas encore assez de ventes pour conseiller un prix." : undefined}>
            <input id="ou" inputMode="numeric" value={f.unit_price_fcfa} onChange={(e) => setF({ ...f, unit_price_fcfa: e.target.value.replace(/\D/g, "") })} className={`${inputCls} tabular-nums`} />
          </Field>
          <Field id="oc" label="Téléphone de contact"><input id="oc" type="tel" value={f.contact_phone} onChange={set("contact_phone")} className={inputCls} /></Field>
          {!!lands.data?.length && (
            <Field id="ol" label="Parcelle d'origine (recommandé)" hint="Une récolte issue d'une parcelle vérifiée inspire confiance aux acheteurs.">
              <select id="ol" value={f.land_id} onChange={set("land_id")} className={inputCls}><option value="">Aucune</option>{lands.data.map((l) => <option key={l.id} value={l.id}>{l.crop_type} · {l.locality ?? l.commune}</option>)}</select>
            </Field>
          )}
          {!f.land_id && (
            <>
              <Field id="ocom" label="Commune"><input id="ocom" value={f.location_commune} onChange={set("location_commune")} className={inputCls} /></Field>
              <Field id="odep" label="Département"><select id="odep" value={f.department} onChange={set("department")} className={inputCls}><option value="">Choisir…</option>{DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}</select></Field>
            </>
          )}
          <div className="sm:col-span-2"><Field id="odesc" label="Description (qualité, conditionnement, livraison)"><textarea id="odesc" rows={3} maxLength={800} value={f.description} onChange={set("description")} className={inputCls} /></Field></div>
        </div>
        {f.quantity_kg && f.unit_price_fcfa && <p className="text-sm">Valeur de l'offre : <strong className="tabular-nums">{formatNumber(Number(f.quantity_kg) * Number(f.unit_price_fcfa))} FCFA</strong></p>}
        {error && <Alert tone="error">{error}</Alert>}
        <Button type="submit" className="w-full min-h-12" loading={busy}
                disabled={f.product_name.trim().length < 2 || !f.quantity_kg || !f.unit_price_fcfa || (!f.land_id && f.location_commune.trim().length < 2)}>
          Publier l'annonce
        </Button>
      </Card>
    </form>
  );
}

// --- Mes annonces --------------------------------------------------------------------------

function MyOfferRow({ offer }: { offer: Offer }) {
  const qc = useQueryClient();
  const [panel, setPanel] = useState<"sold" | "edit" | "interests" | null>(null);
  const [sold, setSold] = useState({ qty: String(offer.quantity_kg), price: String(offer.unit_price_fcfa) });
  const [edit, setEdit] = useState({ quantity_kg: String(offer.quantity_kg), unit_price_fcfa: String(offer.unit_price_fcfa), description: offer.description ?? "" });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["offers"] }); qc.invalidateQueries({ queryKey: ["market"] }); setPanel(null); };
  const status = useMutation({
    mutationFn: async (body: { status: "active" | "sold" | "withdrawn"; sold_quantity_kg?: number; sold_unit_price_fcfa?: number }) =>
      unwrap(await api.PATCH("/api/v1/market/offers/{offer_id}/status", { params: { path: { offer_id: offer.id } }, body })),
    onSuccess: refresh,
  });
  const save = useMutation({
    mutationFn: async () => unwrap(await api.PATCH("/api/v1/market/offers/{offer_id}", { params: { path: { offer_id: offer.id } },
      body: { quantity_kg: Number(edit.quantity_kg), unit_price_fcfa: Number(edit.unit_price_fcfa), description: edit.description || undefined } })),
    onSuccess: refresh,
  });
  const label = { active: ["Disponible", "green"], sold: ["Vendue", "blue"], withdrawn: ["Retirée", "neutral"] } as const;
  const [l, tone] = label[offer.status];
  const interested = offer.interest_count ?? 0;
  return (
    <li className="p-4 border border-neutral-200 rounded-lg space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-bold">{offer.product_name} · <span className="tabular-nums">{formatNumber(offer.quantity_kg)} kg</span> à <span className="tabular-nums">{formatNumber(offer.unit_price_fcfa)} FCFA/kg</span></h3>
          <p className="text-sm text-neutral-600">{offer.location_commune}{offer.status === "sold" && offer.sold_quantity_kg ? ` · vendu ${formatNumber(offer.sold_quantity_kg)} kg à ${formatNumber(offer.sold_unit_price_fcfa ?? 0)} FCFA/kg` : ""}</p>
        </div>
        <div className="flex gap-1.5">{offer.origin_verified && <Badge tone="green">Parcelle vérifiée</Badge>}<Badge tone={tone}>{l}</Badge></div>
      </div>
      <div className="flex flex-wrap gap-2">
        {offer.status === "active" && (
          <>
            <Button onClick={() => setPanel(panel === "sold" ? null : "sold")}>J'ai vendu</Button>
            <Button variant="outline" onClick={() => setPanel(panel === "edit" ? null : "edit")}>Modifier</Button>
            {interested > 0 && <Button variant="soft" onClick={() => setPanel(panel === "interests" ? null : "interests")}>{interested} acheteur{interested > 1 ? "s" : ""} intéressé{interested > 1 ? "s" : ""}</Button>}
            <Button variant="ghost" onClick={() => status.mutate({ status: "withdrawn" })}>Retirer</Button>
          </>
        )}
        {offer.status === "withdrawn" && <Button variant="outline" onClick={() => status.mutate({ status: "active" })}>Remettre en vente</Button>}
      </div>
      {panel === "sold" && (
        <form onSubmit={(e) => { e.preventDefault(); status.mutate({ status: "sold", sold_quantity_kg: Number(sold.qty), sold_unit_price_fcfa: Number(sold.price) }); }} className="grid gap-3 sm:grid-cols-3 items-end p-3 rounded bg-neutral-50 border border-neutral-200">
          <Field id={`sq-${offer.id}`} label="Quantité vendue (kg)"><input id={`sq-${offer.id}`} inputMode="numeric" value={sold.qty} onChange={(e) => setSold({ ...sold, qty: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <Field id={`sp-${offer.id}`} label="Prix obtenu (FCFA/kg)"><input id={`sp-${offer.id}`} inputMode="numeric" value={sold.price} onChange={(e) => setSold({ ...sold, price: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <Button type="submit" loading={status.isPending}>Déclarer la vente</Button>
          <p className="sm:col-span-3 text-xs text-neutral-500">Les ventes déclarées comptent dans votre score et aident à établir les prix de référence.</p>
        </form>
      )}
      {panel === "edit" && (
        <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="grid gap-3 sm:grid-cols-2 items-end p-3 rounded bg-neutral-50 border border-neutral-200">
          <Field id={`eq-${offer.id}`} label="Quantité (kg)"><input id={`eq-${offer.id}`} inputMode="numeric" value={edit.quantity_kg} onChange={(e) => setEdit({ ...edit, quantity_kg: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <Field id={`ep-${offer.id}`} label="Prix (FCFA/kg)"><input id={`ep-${offer.id}`} inputMode="numeric" value={edit.unit_price_fcfa} onChange={(e) => setEdit({ ...edit, unit_price_fcfa: e.target.value.replace(/\D/g, "") })} className={inputCls} /></Field>
          <div className="sm:col-span-2"><Field id={`ed-${offer.id}`} label="Description"><textarea id={`ed-${offer.id}`} rows={2} maxLength={800} value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} className={inputCls} /></Field></div>
          <Button type="submit" className="sm:col-span-2" loading={save.isPending}>Enregistrer</Button>
        </form>
      )}
      {panel === "interests" && <div className="p-3 rounded border border-blue-200 bg-blue-50"><OfferInterests offer={offer} /></div>}
      {(status.isError || save.isError) && <Alert tone="error">{((status.error ?? save.error) as Error).message}</Alert>}
    </li>
  );
}

function MyOffers({ onPublish }: { onPublish: () => void }) {
  const q = useMyOffers();
  return (
    <Card>
      <CardHeader icon={ShoppingBasket} title="Mes annonces" action={<Button className="min-h-9" onClick={onPublish}><Plus className="w-4 h-4" aria-hidden /> Publier</Button>} />
      {q.isLoading && <Loading />}
      {q.isSuccess && !q.data.length && <Empty>Aucune annonce pour le moment.</Empty>}
      <ul className="space-y-3">{q.data?.map((o) => <MyOfferRow key={o.id} offer={o} />)}</ul>
    </Card>
  );
}

// --- Page ------------------------------------------------------------------------------------

type Tab = "catalogue" | "prix" | "mes" | "publier" | "interets";

export function MarketPage() {
  const { user } = useSession();
  const farmer = user?.role === "farmer";
  const tabs: [Tab, string][] = [["catalogue", "Catalogue"], ["prix", "Prix"], ...(farmer ? [["mes", "Mes annonces"], ["publier", "Publier"]] as [Tab, string][] : [["interets", "Mes intérêts"]] as [Tab, string][])];
  const [tab, setTab] = useState<Tab>("catalogue");
  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight">Marché agricole</h1>
            <p className="text-sm text-neutral-600">Mise en relation directe entre producteurs et acheteurs, sans intermédiaire.</p>
          </div>
          <div role="tablist" className="flex gap-1 bg-neutral-100 p-1 rounded border border-neutral-200 overflow-x-auto max-w-full">
            {tabs.map(([t, label]) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                      className={`min-h-10 px-3 rounded text-sm font-semibold cursor-pointer whitespace-nowrap shrink-0 ${tab === t ? "bg-white shadow-sm text-emerald-900" : "text-neutral-600"}`}>{label}</button>
            ))}
          </div>
        </div>
      </Card>
      {tab === "catalogue" && <Catalogue />}
      {tab === "prix" && <Prices />}
      {tab === "mes" && <MyOffers onPublish={() => setTab("publier")} />}
      {tab === "publier" && <PublishForm onDone={() => setTab("mes")} />}
      {tab === "interets" && <Card><CardHeader icon={Heart} title="Offres suivies" /><MyInterests /></Card>}
    </div>
  );
}
