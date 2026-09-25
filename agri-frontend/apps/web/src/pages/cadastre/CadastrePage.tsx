import { api, formatNumber, useSession } from "@agri/core";
import { useQuery } from "@tanstack/react-query";
import { Download, Map as MapIcon, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MapView } from "../../components/MapView";
import { Alert, Badge, Button, buttonClass, Card, CardHeader, Empty, Loading } from "../../components/ui";
import { featureBounds } from "../../lib/geometry";
import { resetBasemap } from "../../lib/map";
import { downloadOfflineMap, offlineMapSize, removeOfflineMap } from "../../lib/offlineMap";
import { unwrap, useMyLands } from "../../lib/queries";
import { useOnline } from "../../lib/useOnline";

function Legend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-600" aria-label="Légende">
      {[["#047857", "Vérifiée"], ["#d97706", "À vérifier"], ["#dc2626", "En litige"], ["#737373", "Non validée"]].map(([c, l]) => (
        <li key={l} className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm" style={{ background: c }} aria-hidden />{l}</li>
      ))}
    </ul>
  );
}

/** Carte gardée dans le téléphone pour le terrain sans réseau. */
function OfflineMapCard() {
  const online = useOnline();
  const [size, setSize] = useState<number | null | undefined>(undefined);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    offlineMapSize().then(setSize);
  }, []);
  const download = async () => {
    setError(null);
    setProgress(0);
    try {
      await downloadOfflineMap(setProgress);
      resetBasemap();
      setSize(await offlineMapSize());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setProgress(null);
    }
  };
  return (
    <div className="p-3 rounded-lg border border-neutral-200 bg-neutral-50 flex flex-wrap items-center justify-between gap-2 text-sm">
      <span>
        <strong>Carte hors ligne</strong> ·{" "}
        {size ? `gardée sur ce téléphone (${formatNumber(size / 1e6, 0)} Mo)` : "pour voir la carte au champ sans réseau"}
      </span>
      {progress !== null ? (
        <span className="tabular-nums font-semibold" aria-live="polite">Téléchargement… {Math.round(progress * 100)} %</span>
      ) : size ? (
        <Button variant="ghost" onClick={async () => { await removeOfflineMap(); resetBasemap(); setSize(null); }}>
          <Trash2 className="w-4 h-4" aria-hidden /> Supprimer
        </Button>
      ) : (
        <Button variant="outline" onClick={download} disabled={!online}>
          <Download className="w-4 h-4" aria-hidden /> Télécharger
        </Button>
      )}
      {error && <div className="w-full"><Alert tone="error">{error}</Alert></div>}
    </div>
  );
}

function FarmerCadastre() {
  const navigate = useNavigate();
  const lands = useMyLands();
  const geo = useQuery({
    queryKey: ["lands", "me", "geojson"],
    queryFn: async () => unwrap(await api.GET("/api/v1/lands/me/geojson")) as unknown as GeoJSON.FeatureCollection,
  });
  const fit = useMemo(() => featureBounds(geo.data), [geo.data]);
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader icon={MapIcon} title={`Mes parcelles (${lands.data?.length ?? 0})`}
                    action={<Link to="/cadastre/nouvelle" className={buttonClass("primary", "min-h-9")}><Plus className="w-4 h-4" aria-hidden /> Ajouter</Link>} />
        <MapView className="h-[55vh] min-h-72" parcels={geo.data} fitBounds={fit} onParcelClick={(id) => navigate(`/cadastre/${id}`)} label="Carte de mes parcelles" />
        <div className="mt-3 space-y-3">
          <Legend />
          <OfflineMapCard />
        </div>
      </Card>
      <Card>
        <CardHeader title="Liste" />
        {lands.isLoading && <Loading />}
        {lands.data?.length === 0 && <Empty>Aucune parcelle. <Link to="/cadastre/nouvelle" className="text-emerald-800 font-semibold underline">Tracer ma première parcelle</Link></Empty>}
        <ul className="divide-y divide-neutral-100">
          {lands.data?.map((l) => (
            <li key={l.id}>
              <Link to={`/cadastre/${l.id}`} className="flex items-center justify-between gap-3 py-3 hover:text-emerald-800">
                <span>
                  <span className="font-semibold">{l.crop_type}</span>
                  <span className="text-sm text-neutral-600"> · {l.commune} · {formatNumber(l.surface_hectares, 2)} ha</span>
                </span>
                {l.dispute_flag ? <Badge tone="red">Litige</Badge> : l.verification_status === "verifiee" ? <Badge tone="green">Vérifiée</Badge> : <Badge tone="amber">À vérifier</Badge>}
              </Link>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

type Filter = "toutes" | "a_verifier" | "litiges" | "verifiees";
const FILTERS: [Filter, string][] = [["toutes", "Toutes"], ["a_verifier", "À vérifier"], ["litiges", "En litige"], ["verifiees", "Vérifiées"]];

/** Carte nationale des agents : chargement de la zone visible uniquement. */
function AgentCadastre() {
  const navigate = useNavigate();
  const [bbox, setBbox] = useState<[number, number, number, number] | null>(null);
  const [filter, setFilter] = useState<Filter>("toutes");
  const limit = 2000;
  const q = useQuery({
    queryKey: ["state", "map", "lands", bbox?.map((v) => v.toFixed(3)).join(","), filter],
    placeholderData: (prev) => prev,
    queryFn: async () => {
      const query: Record<string, string | number | boolean> = { limit };
      if (bbox) query.bbox = bbox.map((v) => v.toFixed(5)).join(",");
      if (filter === "litiges") query.dispute_only = true;
      if (filter === "verifiees") query.verification_status = "verifiee";
      if (filter === "a_verifier") query.verification_status = "declaree";
      return unwrap(await api.GET("/api/v1/state/map/lands", { params: { query: query as never } })) as unknown as GeoJSON.FeatureCollection;
    },
  });
  const count = q.data?.features.length ?? 0;
  return (
    <Card>
      <CardHeader icon={MapIcon} title="Cadastre national" action={<span className="text-sm text-neutral-600 tabular-nums">{count} parcelle{count > 1 ? "s" : ""} affichée{count > 1 ? "s" : ""}</span>} />
      <div className="flex flex-wrap gap-2 mb-3" role="group" aria-label="Filtrer les parcelles">
        {FILTERS.map(([f, label]) => (
          <button type="button" key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
                  className={`min-h-9 px-3 rounded-full border text-sm font-semibold cursor-pointer ${filter === f ? "bg-emerald-800 border-emerald-800 text-white" : "border-neutral-300 text-neutral-700 hover:bg-neutral-50"}`}>
            {label}
          </button>
        ))}
      </div>
      <MapView className="h-[62vh] min-h-80" parcels={q.data} onViewChange={setBbox} onParcelClick={(id) => navigate(`/cadastre/${id}`)} label="Carte nationale des parcelles" />
      <div className="mt-3 space-y-2">
        <Legend />
        {count >= limit && <Alert tone="info">Affichage limité à {limit} parcelles : zoomez pour voir le détail.</Alert>}
      </div>
    </Card>
  );
}

export function CadastrePage() {
  const { user } = useSession();
  return user?.role === "farmer" ? <FarmerCadastre /> : <AgentCadastre />;
}
