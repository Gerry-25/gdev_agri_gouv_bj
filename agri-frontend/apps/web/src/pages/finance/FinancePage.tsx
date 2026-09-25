import { authStore, useSession } from "@agri/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertOctagon,
  ArrowRight,
  Award,
  Banknote,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileText,
  Landmark,
  RefreshCw,
  Search,
  Sparkles,
  X,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  Loading,
  Metric,
} from "../../components/ui";

const API_ORIGIN = import.meta.env.VITE_API_URL || "";

const DEPARTMENTS = [
  "Alibori", "Atacora", "Atlantique", "Borgou", "Collines", "Couffo",
  "Donga", "Littoral", "Mono", "Ouémé", "Plateau", "Zou",
];

// --- Interfaces ---

interface FinancialOffer {
  id: string;
  title: string;
  type: "credit" | "assurance" | "financement";
  category_label: string;
  institution: string;
  description: string;
  amount_min: number;
  amount_max: number;
  currency: string;
  interest_rate_pct?: number | null;
  duration_months?: number | null;
  grace_period_months?: number | null;
  premium_rate_pct?: number | null;
  coverage_details?: string | null;
  subsidy_pct?: number | null;
  eligible_departments: string[];
  eligible_crops: string[];
  min_performance_score?: number | null;
  requirements: string[];
  active: boolean;
  created_at: string;
  updated_at: string;
}

interface FinancialAiEvaluation {
  score: number;
  verdict: "favorable" | "favorable_sous_conditions" | "defavorable";
  verdict_label: string;
  strengths: string[];
  risks: string[];
  recommended_conditions: string[];
  recommended_amount?: number | null;
  summary: string;
  farmer_advice: string;
  type_specific_metrics: Record<string, any>;
}

interface FinancialApplication {
  id: string;
  offer_id: string;
  offer_title: string;
  offer_type: "credit" | "assurance" | "financement";
  offer_institution: string;
  farmer_npi: string;
  farmer_name: string;
  farmer_phone: string;
  department: string;
  commune: string;
  land_id?: string | null;
  land_title?: string | null;
  crop_type: string;
  surface_ha: number;
  amount_requested: number;
  amount_approved?: number | null;
  project_description: string;
  declared_harvest_estimate_kg?: number | null;
  guarantees_or_notes?: string | null;
  status: "soumis" | "analyse_ia" | "approuve" | "rejete" | "debourse_actif" | "clos";
  ai_evaluation?: FinancialAiEvaluation | null;
  agent_decision?: {
    status: string;
    decided_by_npi: string;
    decided_by_name: string;
    amount_approved?: number | null;
    interest_rate_approved?: number | null;
    duration_approved_months?: number | null;
    conditions: string[];
    motivation_or_notes: string;
    decided_at: string;
  } | null;
  disbursement?: {
    disbursed_at: string;
    contract_ref: string;
    payment_reference?: string | null;
    disbursed_by: string;
    notes?: string | null;
  } | null;
  created_at: string;
  updated_at: string;
}

interface FinanceStats {
  total_applications: number;
  pending_applications: number;
  approved_applications: number;
  rejected_applications: number;
  disbursed_applications: number;
  total_amount_requested: number;
  total_amount_approved: number;
  by_type: Record<string, number>;
  by_status: Record<string, number>;
  by_department: Record<string, number>;
  approval_rate_pct: number;
}

interface FarmerLand {
  id: string;
  title: string;
  department: string;
  commune: string;
  surface_hectares: number;
  verification_status: string;
  dispute_flag: boolean;
}

// --- API Helpers ---

async function fetchWithAuth<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = authStore.get().accessToken;
  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_ORIGIN}${path}`, { ...options, headers });
  if (!res.ok) {
    const errorData = await res.json().catch(() => null);
    throw new Error(errorData?.detail || `Erreur serveur (${res.status})`);
  }
  return res.json();
}

function formatFcfa(val?: number | null): string {
  if (val === null || val === undefined) return "0 FCFA";
  return new Intl.NumberFormat("fr-FR").format(Math.round(val)) + " FCFA";
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

const inputCls = "w-full px-3 py-2 text-sm border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";

// --- Badges & Helpers ---

function getTypeBadge(type: string) {
  switch (type) {
    case "credit":
      return <Badge tone="blue">💳 Crédit Agricole</Badge>;
    case "assurance":
      return <Badge tone="amber">🛡️ Assurance Indicielle</Badge>;
    case "financement":
      return <Badge tone="green">🏛️ Subvention d'État</Badge>;
    default:
      return <Badge tone="neutral">{type}</Badge>;
  }
}

function getStatusBadge(status: string) {
  switch (status) {
    case "soumis":
      return <Badge tone="amber">⏳ En attente d'instruction</Badge>;
    case "analyse_ia":
      return <Badge tone="purple">🤖 Analyse IA en cours</Badge>;
    case "approuve":
      return <Badge tone="green">✅ Approuvé</Badge>;
    case "rejete":
      return <Badge tone="red">❌ Refusé</Badge>;
    case "debourse_actif":
      return <Badge tone="green">🎉 Contrat Actif / Déboursé</Badge>;
    case "clos":
      return <Badge tone="neutral">📁 Archivé</Badge>;
    default:
      return <Badge tone="neutral">{status}</Badge>;
  }
}

function getVerdictBadge(verdict: string) {
  switch (verdict) {
    case "favorable":
      return <Badge tone="green">🌟 Avis Favorable</Badge>;
    case "favorable_sous_conditions":
      return <Badge tone="amber">⚠️ Favorable sous Réserves</Badge>;
    case "defavorable":
      return <Badge tone="red">⛔ Avis Défavorable</Badge>;
    default:
      return <Badge tone="neutral">{verdict}</Badge>;
  }
}

// ============================================================================
// COMPOSANT PRINCIPAL
// ============================================================================

export function FinancePage() {
  const { user } = useSession();
  const queryClient = useQueryClient();
  const isAgent = user?.role === "state_agent" || user?.role === "state_supervisor";

  // Farmer state
  const [farmerTab, setFarmerTab] = useState<"catalog" | "my_applications">("catalog");
  const [selectedOfferForApply, setSelectedOfferForApply] = useState<FinancialOffer | null>(null);

  // Agent state
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [deptFilter, setDeptFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedAppForReview, setSelectedAppForReview] = useState<FinancialApplication | null>(null);

  // Queries
  const offersQuery = useQuery({
    queryKey: ["finance", "offers"],
    queryFn: () => fetchWithAuth<FinancialOffer[]>("/api/v1/finance/offers"),
  });

  const myApplicationsQuery = useQuery({
    queryKey: ["finance", "applications", "me"],
    queryFn: () => fetchWithAuth<FinancialApplication[]>("/api/v1/finance/applications/me"),
    enabled: !isAgent,
  });

  const allApplicationsQuery = useQuery({
    queryKey: ["finance", "applications", statusFilter, typeFilter, deptFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (typeFilter) params.set("type", typeFilter);
      if (deptFilter) params.set("department", deptFilter);
      return fetchWithAuth<FinancialApplication[]>(`/api/v1/finance/applications?${params.toString()}`);
    },
    enabled: isAgent,
  });

  const statsQuery = useQuery({
    queryKey: ["finance", "stats"],
    queryFn: () => fetchWithAuth<FinanceStats>("/api/v1/finance/stats"),
    enabled: isAgent,
  });

  const myLandsQuery = useQuery({
    queryKey: ["lands", "me"],
    queryFn: () => fetchWithAuth<FarmerLand[]>("/api/v1/lands/me"),
    enabled: !isAgent,
  });

  return (
    <div className="space-y-6">
      {/* En-tête de la page */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-neutral-200 pb-4">
        <div className="flex items-center gap-3">
          <span className="p-2.5 rounded-xl bg-emerald-100 text-emerald-900 border border-emerald-300">
            <Landmark className="w-6 h-6" />
          </span>
          <div>
            <h1 className="text-xl sm:text-2xl font-black text-neutral-950">
              Financement, Crédit & Assurance Agricole
            </h1>
            <p className="text-xs sm:text-sm text-neutral-600">
              {isAgent
                ? "Guichet d'instruction des demandes de prêt, assurance indicielle et subventions FNDA / MAEP."
                : "Accédez aux crédits de campagne, assurances multirisques et subventions d'État pour sécuriser vos récoltes."}
            </p>
          </div>
        </div>

        {!isAgent && (
          <div className="flex items-center bg-neutral-100 p-1 rounded-lg border border-neutral-200">
            <button
              onClick={() => setFarmerTab("catalog")}
              className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all ${
                farmerTab === "catalog"
                  ? "bg-white text-emerald-900 shadow-sm"
                  : "text-neutral-600 hover:text-neutral-900"
              }`}
            >
              Catalogue des offres ({offersQuery.data?.length || 0})
            </button>
            <button
              onClick={() => setFarmerTab("my_applications")}
              className={`px-3 py-1.5 rounded-md text-xs font-bold transition-all ${
                farmerTab === "my_applications"
                  ? "bg-white text-emerald-900 shadow-sm"
                  : "text-neutral-600 hover:text-neutral-900"
              }`}
            >
              Mes dossiers ({myApplicationsQuery.data?.length || 0})
            </button>
          </div>
        )}
      </div>

      {/* VUE EXPLOITANT */}
      {!isAgent && (
        <>
          {farmerTab === "catalog" && (
            <FarmerOffersCatalog
              offers={offersQuery.data || []}
              isLoading={offersQuery.isLoading}
              onApply={(offer) => setSelectedOfferForApply(offer)}
            />
          )}

          {farmerTab === "my_applications" && (
            <FarmerMyApplications
              applications={myApplicationsQuery.data || []}
              isLoading={myApplicationsQuery.isLoading}
              onGoCatalog={() => setFarmerTab("catalog")}
            />
          )}
        </>
      )}

      {/* VUE AGENT / SUPERVISEUR */}
      {isAgent && (
        <AgentFinanceCockpit
          stats={statsQuery.data}
          applications={allApplicationsQuery.data || []}
          isLoading={allApplicationsQuery.isLoading || statsQuery.isLoading}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          typeFilter={typeFilter}
          setTypeFilter={setTypeFilter}
          deptFilter={deptFilter}
          setDeptFilter={setDeptFilter}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          onReview={(app) => setSelectedAppForReview(app)}
        />
      )}

      {/* MODAL : Postuler à une offre (Exploitant) */}
      {selectedOfferForApply && (
        <ApplyModal
          offer={selectedOfferForApply}
          farmerLands={myLandsQuery.data || []}
          onClose={() => setSelectedOfferForApply(null)}
          onSuccess={() => {
            setSelectedOfferForApply(null);
            setFarmerTab("my_applications");
            queryClient.invalidateQueries({ queryKey: ["finance"] });
          }}
        />
      )}

      {/* MODAL : Revue & Décision du dossier (Agent/Superviseur) */}
      {selectedAppForReview && (
        <ReviewApplicationModal
          application={selectedAppForReview}
          onClose={() => setSelectedAppForReview(null)}
          onSuccess={(updated) => {
            setSelectedAppForReview(updated);
            queryClient.invalidateQueries({ queryKey: ["finance"] });
          }}
        />
      )}
    </div>
  );
}

// ============================================================================
// COMPOSANT : Catalogue des offres (Exploitant)
// ============================================================================

function FarmerOffersCatalog({
  offers,
  isLoading,
  onApply,
}: {
  offers: FinancialOffer[];
  isLoading: boolean;
  onApply: (offer: FinancialOffer) => void;
}) {
  const [selectedType, setSelectedType] = useState<string>("");
  const [search, setSearch] = useState<string>("");

  const filtered = useMemo(() => {
    return offers.filter((o) => {
      if (selectedType && o.type !== selectedType) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          o.title.toLowerCase().includes(q) ||
          o.institution.toLowerCase().includes(q) ||
          o.description.toLowerCase().includes(q) ||
          o.category_label.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [offers, selectedType, search]);

  return (
    <div className="space-y-4">
      {/* Filtres rapides */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setSelectedType("")}
            className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all ${
              !selectedType
                ? "bg-emerald-800 text-white shadow-sm"
                : "bg-neutral-100 text-neutral-700 hover:bg-neutral-200"
            }`}
          >
            Tous ({offers.length})
          </button>
          <button
            onClick={() => setSelectedType("credit")}
            className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all ${
              selectedType === "credit"
                ? "bg-blue-700 text-white shadow-sm"
                : "bg-neutral-100 text-neutral-700 hover:bg-neutral-200"
            }`}
          >
            💳 Crédits Intrants & Équipement
          </button>
          <button
            onClick={() => setSelectedType("assurance")}
            className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all ${
              selectedType === "assurance"
                ? "bg-amber-700 text-white shadow-sm"
                : "bg-neutral-100 text-neutral-700 hover:bg-neutral-200"
            }`}
          >
            🛡️ Assurances Indicielles Climat
          </button>
          <button
            onClick={() => setSelectedType("financement")}
            className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all ${
              selectedType === "financement"
                ? "bg-emerald-700 text-white shadow-sm"
                : "bg-neutral-100 text-neutral-700 hover:bg-neutral-200"
            }`}
          >
            🏛️ Subventions d'État & Primes
          </button>
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 text-neutral-400 absolute left-2.5 top-2.5" />
          <input
            type="text"
            placeholder="Rechercher une offre..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={`${inputCls} pl-8`}
          />
        </div>
      </div>

      {isLoading && <Loading label="Chargement des opportunités de financement..." />}

      {!isLoading && filtered.length === 0 && (
        <Empty>
          <p className="font-semibold text-neutral-800">Aucune offre trouvée.</p>
          <p className="text-xs text-neutral-500 mt-1">
            Modifiez vos filtres de recherche pour consulter les autres opportunités.
          </p>
        </Empty>
      )}

      {/* Grille des offres */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((offer) => (
          <div
            key={offer.id}
            className="flex flex-col justify-between p-4 rounded-xl border border-neutral-200 bg-white hover:border-emerald-700 hover:shadow-md transition-all group"
          >
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                {getTypeBadge(offer.type)}
                <span className="text-xs font-bold text-neutral-600 bg-neutral-100 px-2 py-0.5 rounded">
                  {offer.institution}
                </span>
              </div>

              <div>
                <h3 className="font-bold text-neutral-950 text-base group-hover:text-emerald-900 transition-colors">
                  {offer.title}
                </h3>
                <p className="text-xs text-neutral-500 mt-0.5">{offer.category_label}</p>
              </div>

              <p className="text-xs text-neutral-600 line-clamp-3 leading-relaxed">
                {offer.description}
              </p>

              {/* Ratios & Conditions financières */}
              <div className="p-2.5 rounded-lg bg-neutral-50 border border-neutral-200 text-xs space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-neutral-500">Montant accessible :</span>
                  <span className="font-bold text-neutral-900">
                    {formatFcfa(offer.amount_min)} à {formatFcfa(offer.amount_max)}
                  </span>
                </div>

                {offer.type === "credit" && (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-neutral-500">Taux d'intérêt annuel :</span>
                      <span className="font-bold text-blue-800">
                        {offer.interest_rate_pct ?? "3.5"} % / an
                      </span>
                    </div>
                    {offer.duration_months && (
                      <div className="flex items-center justify-between">
                        <span className="text-neutral-500">Durée maximale :</span>
                        <span className="font-medium text-neutral-800">
                          {offer.duration_months} mois (différé {offer.grace_period_months || 0} mois)
                        </span>
                      </div>
                    )}
                  </>
                )}

                {offer.type === "assurance" && (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-neutral-500">Prime indicielle :</span>
                      <span className="font-bold text-amber-800">
                        {offer.premium_rate_pct ?? "4.0"} % de la valeur assurée
                      </span>
                    </div>
                    {offer.coverage_details && (
                      <div className="text-[11px] text-neutral-600 pt-0.5 border-t border-neutral-200">
                        🛡️ {offer.coverage_details}
                      </div>
                    )}
                  </>
                )}

                {offer.type === "financement" && (
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-500">Taux subventionné :</span>
                    <span className="font-bold text-emerald-800">
                      Jusqu'à {offer.subsidy_pct ?? "70"} % pris en charge
                    </span>
                  </div>
                )}
              </div>

              {/* Critères d'éligibilité */}
              {offer.requirements?.length > 0 && (
                <div className="space-y-1">
                  <span className="text-[11px] font-bold text-neutral-500 uppercase tracking-wider">
                    Conditions requises
                  </span>
                  <ul className="text-xs text-neutral-600 space-y-1">
                    {offer.requirements.slice(0, 3).map((r, idx) => (
                      <li key={idx} className="flex items-center gap-1.5">
                        <CheckCircle2 className="w-3 h-3 text-emerald-700 shrink-0" />
                        <span className="truncate">{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="pt-4 border-t border-neutral-100 mt-4">
              <Button
                variant="primary"
                onClick={() => onApply(offer)}
                className="w-full text-xs font-bold"
              >
                Postuler à cette offre <ArrowRight className="w-3.5 h-3.5 ml-1" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// COMPOSANT : Mes dossiers de financement (Exploitant)
// ============================================================================

function FarmerMyApplications({
  applications,
  isLoading,
  onGoCatalog,
}: {
  applications: FinancialApplication[];
  isLoading: boolean;
  onGoCatalog: () => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (isLoading) return <Loading label="Chargement de vos dossiers financiers..." />;

  if (applications.length === 0) {
    return (
      <Empty>
        <p className="font-semibold text-neutral-800">Vous n'avez soumis aucun dossier de financement.</p>
        <p className="text-xs text-neutral-500 mt-1 max-w-md mx-auto">
          Explorez le catalogue officiel pour solliciter un microcrédit de campagne, une assurance sécheresse ou une subvention pour vos cultures.
        </p>
        <Button variant="primary" onClick={onGoCatalog} className="mt-4 text-xs">
          Parcourir les offres disponibles
        </Button>
      </Empty>
    );
  }

  return (
    <div className="space-y-4">
      {applications.map((app) => {
        const isExpanded = expandedId === app.id;
        const ai = app.ai_evaluation;
        const dec = app.agent_decision;

        return (
          <Card key={app.id} className="p-4 sm:p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-neutral-100 pb-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  {getTypeBadge(app.offer_type)}
                  <h3 className="font-bold text-base text-neutral-950">{app.offer_title}</h3>
                  <span className="text-xs text-neutral-500">· {app.offer_institution}</span>
                </div>
                <div className="text-xs text-neutral-500">
                  Dossier déposé le {formatDate(app.created_at)} · {app.commune}, {app.department}
                </div>
              </div>

              <div className="flex items-center gap-2">
                {getStatusBadge(app.status)}
              </div>
            </div>

            {/* Chiffres clés */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3 rounded-lg bg-neutral-50 border border-neutral-200 text-xs">
              <div>
                <span className="text-neutral-500 block">Montant sollicité :</span>
                <span className="font-bold text-sm text-neutral-900">{formatFcfa(app.amount_requested)}</span>
              </div>
              <div>
                <span className="text-neutral-500 block">Culture & Surface :</span>
                <span className="font-bold text-neutral-900">{app.crop_type} ({app.surface_ha} ha)</span>
              </div>
              <div>
                <span className="text-neutral-500 block">Montant accordé :</span>
                <span className="font-bold text-sm text-emerald-800">
                  {app.amount_approved ? formatFcfa(app.amount_approved) : "En cours d'étude"}
                </span>
              </div>
              <div>
                <span className="text-neutral-500 block">Évaluation IA :</span>
                <span className="font-bold flex items-center gap-1">
                  {ai ? (
                    <>
                      <span className="text-neutral-900">{ai.score}/100</span>
                      {getVerdictBadge(ai.verdict)}
                    </>
                  ) : (
                    "Calcul en cours..."
                  )}
                </span>
              </div>
            </div>

            {/* Décision officielle de l'agent si disponible */}
            {dec && (
              <div className={`p-3.5 rounded-lg border text-xs space-y-1.5 ${
                dec.status === "approuve" ? "bg-emerald-50 border-emerald-300 text-emerald-950" : "bg-red-50 border-red-300 text-red-950"
              }`}>
                <div className="flex items-center justify-between font-bold">
                  <span className="flex items-center gap-1.5">
                    {dec.status === "approuve" ? <CheckCircle2 className="w-4 h-4 text-emerald-700" /> : <XCircle className="w-4 h-4 text-red-700" />}
                    Décision officielle : {dec.status === "approuve" ? "Dossier Validé" : "Demande Refusée"}
                  </span>
                  <span className="text-[11px] font-normal text-neutral-600">
                    Par {dec.decided_by_name} le {formatDate(dec.decided_at)}
                  </span>
                </div>
                <p className="leading-relaxed">{dec.motivation_or_notes}</p>
                {dec.conditions?.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-emerald-200/60">
                    <span className="font-bold block mb-1">Conditions d'octroi fixées :</span>
                    <ul className="list-disc pl-4 space-y-0.5">
                      {dec.conditions.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Contrat actif / Déboursement */}
            {app.disbursement && (
              <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-950 flex items-center justify-between">
                <div>
                  <span className="font-bold block">Contrat Actif / Fonds Débloqués</span>
                  <span className="text-blue-800">
                    Réf. contrat : <strong>{app.disbursement.contract_ref}</strong>
                  </span>
                </div>
                <Badge tone="blue">Contrat en vigueur</Badge>
              </div>
            )}

            {/* Bouton pour déplier l'analyse IA détaillée */}
            {ai && (
              <div>
                <button
                  onClick={() => setExpandedId(isExpanded ? null : app.id)}
                  className="inline-flex items-center gap-1 text-xs font-bold text-emerald-800 hover:underline"
                >
                  <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
                  {isExpanded ? "Masquer les détails de l'analyse IA" : "Voir l'analyse détaillée du dossier par l'IA"}
                  {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>

                {isExpanded && (
                  <div className="mt-3 p-4 rounded-xl bg-neutral-50 border border-neutral-200 space-y-3 text-xs">
                    <div className="flex items-center justify-between border-b border-neutral-200 pb-2">
                      <div className="font-bold text-sm text-neutral-900 flex items-center gap-2">
                        <Award className="w-4 h-4 text-emerald-700" />
                        Score d'éligibilité agronomique et financière : {ai.score}/100
                      </div>
                      {getVerdictBadge(ai.verdict)}
                    </div>

                    <p className="text-neutral-700 leading-relaxed italic bg-white p-2.5 rounded border border-neutral-200">
                      "{ai.summary}"
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div className="p-2.5 rounded bg-emerald-50/70 border border-emerald-200">
                        <span className="font-bold text-emerald-950 flex items-center gap-1 mb-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-700" /> Points forts du profil
                        </span>
                        <ul className="list-disc pl-4 space-y-1 text-emerald-900">
                          {ai.strengths.map((s, idx) => (
                            <li key={idx}>{s}</li>
                          ))}
                        </ul>
                      </div>

                      <div className="p-2.5 rounded bg-amber-50/70 border border-amber-200">
                        <span className="font-bold text-amber-950 flex items-center gap-1 mb-1.5">
                          <AlertCircle className="w-3.5 h-3.5 text-amber-700" /> Points de vigilance
                        </span>
                        <ul className="list-disc pl-4 space-y-1 text-amber-900">
                          {ai.risks.map((r, idx) => (
                            <li key={idx}>{r}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {ai.farmer_advice && (
                      <div className="p-2.5 rounded bg-blue-50 border border-blue-200 text-blue-950">
                        <span className="font-bold block mb-1">💡 Recommandation agronomique personnalisée :</span>
                        <p>{ai.farmer_advice}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}

// ============================================================================
// COMPOSANT : Modal de candidature (Exploitant)
// ============================================================================

function ApplyModal({
  offer,
  farmerLands,
  onClose,
  onSuccess,
}: {
  offer: FinancialOffer;
  farmerLands: FarmerLand[];
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [selectedLandId, setSelectedLandId] = useState<string>("");
  const [cropType, setCropType] = useState<string>(offer.eligible_crops?.[0] || "Maïs");
  const [surfaceHa, setSurfaceHa] = useState<number>(1.0);
  const [amountRequested, setAmountRequested] = useState<number>(
    Math.min(Math.max(offer.amount_min, 500000), offer.amount_max)
  );
  const [declaredYieldKg, setDeclaredYieldKg] = useState<number>(2500);
  const [projectDescription, setProjectDescription] = useState<string>("");
  const [guarantees, setGuarantees] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");

  // Pré-remplissage surface si choix de parcelle
  const handleLandSelect = (landId: string) => {
    setSelectedLandId(landId);
    const land = farmerLands.find((l) => l.id === landId);
    if (land && land.surface_hectares > 0) {
      setSurfaceHa(land.surface_hectares);
    }
  };

  const applyMutation = useMutation({
    mutationFn: () => {
      if (amountRequested < offer.amount_min || amountRequested > offer.amount_max) {
        throw new Error(
          `Le montant doit être compris entre ${formatFcfa(offer.amount_min)} et ${formatFcfa(offer.amount_max)}`
        );
      }
      if (!projectDescription.trim() || projectDescription.trim().length < 10) {
        throw new Error("Veuillez décrire brièvement l'objet de votre projet (au moins 10 caractères).");
      }

      return fetchWithAuth("/api/v1/finance/applications", {
        method: "POST",
        body: JSON.stringify({
          offer_id: offer.id,
          land_id: selectedLandId || null,
          crop_type: cropType,
          surface_ha: Number(surfaceHa),
          amount_requested: Number(amountRequested),
          project_description: projectDescription,
          declared_harvest_estimate_kg: Number(declaredYieldKg) || null,
          guarantees_or_notes: guarantees || null,
        }),
      });
    },
    onSuccess: () => {
      onSuccess();
    },
    onError: (err: any) => {
      setErrorMsg(err.message || "Erreur lors du dépôt de la candidature.");
    },
  });

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl max-w-xl w-full p-5 sm:p-6 space-y-4 shadow-xl border border-neutral-200 my-8">
        <div className="flex items-center justify-between border-b border-neutral-100 pb-3">
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-lg bg-emerald-100 text-emerald-900">
              <Banknote className="w-5 h-5" />
            </span>
            <div>
              <h2 className="font-bold text-base text-neutral-950">Postuler à l'offre</h2>
              <p className="text-xs text-neutral-500">{offer.title} · {offer.institution}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        {errorMsg && <Alert tone="error">{errorMsg}</Alert>}

        <div className="space-y-3.5 text-xs">
          {/* Sélection de la parcelle */}
          <div>
            <label className="block font-bold text-neutral-700 mb-1">
              Parcelle de culture concernée (recommandé)
            </label>
            <select
              value={selectedLandId}
              onChange={(e) => handleLandSelect(e.target.value)}
              className={inputCls}
            >
              <option value="">Sélectionner une parcelle cadastrée...</option>
              {farmerLands.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.title} ({l.surface_hectares} ha - {l.commune}) {l.verification_status === "verifiee" ? "✓ Vérifiée" : ""}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-bold text-neutral-700 mb-1">Spéculation / Culture</label>
              <input
                type="text"
                value={cropType}
                onChange={(e) => setCropType(e.target.value)}
                placeholder="Ex: Maïs, Coton, Soja..."
                className={inputCls}
              />
            </div>
            <div>
              <label className="block font-bold text-neutral-700 mb-1">Surface cultivée (hectares)</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={surfaceHa}
                onChange={(e) => setSurfaceHa(Number(e.target.value))}
                className={inputCls}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block font-bold text-neutral-700 mb-1">
                Montant demandé (FCFA)
              </label>
              <input
                type="number"
                step="50000"
                min={offer.amount_min}
                max={offer.amount_max}
                value={amountRequested}
                onChange={(e) => setAmountRequested(Number(e.target.value))}
                className={inputCls}
              />
              <span className="text-[10px] text-neutral-500 mt-0.5 block">
                Fourchette autorisée : {formatFcfa(offer.amount_min)} à {formatFcfa(offer.amount_max)}
              </span>
            </div>

            <div>
              <label className="block font-bold text-neutral-700 mb-1">
                Estimation récolte attendue (kg)
              </label>
              <input
                type="number"
                step="100"
                value={declaredYieldKg}
                onChange={(e) => setDeclaredYieldKg(Number(e.target.value))}
                className={inputCls}
              />
            </div>
          </div>

          <div>
            <label className="block font-bold text-neutral-700 mb-1">
              Description du projet & Utilisation prévue des fonds
            </label>
            <textarea
              rows={3}
              value={projectDescription}
              onChange={(e) => setProjectDescription(e.target.value)}
              placeholder="Expliquez vos besoins (achat semences certifiées, engrais NPK, mécanisation, préparation des sols, main-d'œuvre)..."
              className={inputCls}
            />
          </div>

          <div>
            <label className="block font-bold text-neutral-700 mb-1">
              Garanties proposées ou plan de remboursement indicatif
            </label>
            <input
              type="text"
              value={guarantees}
              onChange={(e) => setGuarantees(e.target.value)}
              placeholder="Ex: Nantissement sur récolte future, caution solidaire de coopérative, titres de propriété..."
              className={inputCls}
            />
          </div>

          <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-[11px] text-emerald-950 flex items-start gap-2">
            <Sparkles className="w-4 h-4 text-emerald-700 shrink-0 mt-0.5" />
            <p>
              Dès la soumission, votre dossier sera évalué instantanément par le moteur d'analyse IA selon votre historique de récolte et la solvabilité agronomique.
            </p>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-3 border-t border-neutral-100">
          <Button variant="outline" onClick={onClose} className="text-xs">
            Annuler
          </Button>
          <Button
            variant="primary"
            onClick={() => applyMutation.mutate()}
            loading={applyMutation.isPending}
            className="text-xs font-bold"
          >
            Déposer ma demande
          </Button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// COMPOSANT : Vue Cockpit Agent & Superviseur
// ============================================================================

function AgentFinanceCockpit({
  stats,
  applications,
  isLoading,
  statusFilter,
  setStatusFilter,
  typeFilter,
  setTypeFilter,
  deptFilter,
  setDeptFilter,
  searchQuery,
  setSearchQuery,
  onReview,
}: {
  stats?: FinanceStats;
  applications: FinancialApplication[];
  isLoading: boolean;
  statusFilter: string;
  setStatusFilter: (v: string) => void;
  typeFilter: string;
  setTypeFilter: (v: string) => void;
  deptFilter: string;
  setDeptFilter: (v: string) => void;
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  onReview: (app: FinancialApplication) => void;
}) {
  const filtered = useMemo(() => {
    return applications.filter((app) => {
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (
        app.farmer_name.toLowerCase().includes(q) ||
        app.farmer_phone.toLowerCase().includes(q) ||
        app.commune.toLowerCase().includes(q) ||
        app.crop_type.toLowerCase().includes(q) ||
        app.offer_title.toLowerCase().includes(q)
      );
    });
  }, [applications, searchQuery]);

  return (
    <div className="space-y-6">
      {/* Cartes de synthèse KPIs */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Card
            onClick={() => {
              setStatusFilter("");
              setTypeFilter("");
              setDeptFilter("");
              setSearchQuery("");
            }}
            className={`p-3.5 cursor-pointer transition-all hover:shadow-sm ${
              !statusFilter && !typeFilter && !deptFilter && !searchQuery
                ? "bg-neutral-100 ring-2 ring-emerald-700 font-bold"
                : "bg-neutral-50 hover:bg-neutral-100/70"
            }`}
          >
            <Metric
              label="Total dossiers"
              value={stats.total_applications}
              hint={formatFcfa(stats.total_amount_requested)}
            />
          </Card>

          <Card
            onClick={() => setStatusFilter(statusFilter === "soumis" ? "" : "soumis")}
            className={`p-3.5 cursor-pointer transition-all hover:shadow-sm ${
              statusFilter === "soumis"
                ? "bg-amber-100 ring-2 ring-amber-600 border-amber-400"
                : stats.pending_applications > 0
                ? "bg-amber-50/70 border-amber-200 hover:bg-amber-100/50"
                : "bg-neutral-50"
            }`}
          >
            <Metric
              label="En attente"
              value={stats.pending_applications}
              hint="À instruire"
              hintTone={stats.pending_applications > 0 ? "amber" : "neutral"}
            />
          </Card>

          <Card
            onClick={() => setStatusFilter(statusFilter === "approuve" ? "" : "approuve")}
            className={`p-3.5 cursor-pointer transition-all hover:shadow-sm ${
              statusFilter === "approuve"
                ? "bg-emerald-100 ring-2 ring-emerald-600 border-emerald-400"
                : "bg-emerald-50/60 border-emerald-200 hover:bg-emerald-100/50"
            }`}
          >
            <Metric
              label="Approuvés"
              value={stats.approved_applications}
              hint={formatFcfa(stats.total_amount_approved)}
              hintTone="green"
            />
          </Card>

          <Card
            onClick={() => setStatusFilter(statusFilter === "rejete" ? "" : "rejete")}
            className={`p-3.5 cursor-pointer transition-all hover:shadow-sm ${
              statusFilter === "rejete"
                ? "bg-red-100 ring-2 ring-red-600 border-red-400"
                : "bg-neutral-50 hover:bg-neutral-100/50"
            }`}
          >
            <Metric
              label="Refusés"
              value={stats.rejected_applications}
              hint="Critères non remplis"
            />
          </Card>

          <Card
            onClick={() => setStatusFilter(statusFilter === "debourse_actif" ? "" : "debourse_actif")}
            className={`p-3.5 cursor-pointer transition-all hover:shadow-sm ${
              statusFilter === "debourse_actif"
                ? "bg-blue-100 ring-2 ring-blue-600 border-blue-400"
                : "bg-blue-50/60 border-blue-200 hover:bg-blue-100/50"
            }`}
          >
            <Metric
              label="Déboursés / Actifs"
              value={stats.disbursed_applications}
              hint={`${stats.approval_rate_pct} % taux d'accord`}
              hintTone="blue"
            />
          </Card>
        </div>
      )}

      {/* Barre de recherche et de filtres */}
      <Card className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-neutral-500">
            Filtres d'instruction
          </span>
          {(statusFilter || typeFilter || deptFilter || searchQuery) && (
            <Button
              variant="ghost"
              onClick={() => {
                setStatusFilter("");
                setTypeFilter("");
                setDeptFilter("");
                setSearchQuery("");
              }}
              className="text-xs text-neutral-600 hover:text-neutral-900 h-7 px-2"
            >
              Afficher tout l'existant (Effacer les filtres)
            </Button>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="block text-xs font-semibold text-neutral-600 mb-1">Recherche</label>
            <div className="relative">
              <Search className="w-4 h-4 text-neutral-400 absolute left-2.5 top-2.5" />
              <input
                type="text"
                placeholder="Producteur, commune, culture..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className={`${inputCls} pl-8`}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-600 mb-1">Type d'offre</label>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className={inputCls}
            >
              <option value="">Tous les types</option>
              <option value="credit">💳 Crédit</option>
              <option value="assurance">🛡️ Assurance</option>
              <option value="financement">🏛️ Financement / Subvention</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-600 mb-1">Statut d'instruction</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className={inputCls}
            >
              <option value="">Tous les statuts</option>
              <option value="soumis">En attente d'instruction</option>
              <option value="approuve">Approuvé</option>
              <option value="rejete">Refusé</option>
              <option value="debourse_actif">Contrat actif / Déboursé</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-600 mb-1">Département</label>
            <select
              value={deptFilter}
              onChange={(e) => setDeptFilter(e.target.value)}
              className={inputCls}
            >
              <option value="">Tous les départements</option>
              {DEPARTMENTS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {/* Liste des candidatures */}
      <Card>
        <CardHeader
          icon={FileText}
          title={`Dossiers de financement enregistrés (${filtered.length})`}
        />

        {isLoading && <Loading label="Chargement des dossiers..." />}

        {!isLoading && filtered.length === 0 && (
          <Empty>
            <p className="font-semibold text-neutral-800">Aucun dossier trouvé avec les filtres sélectionnés.</p>
            {(statusFilter || typeFilter || deptFilter || searchQuery) && (
              <Button
                variant="outline"
                onClick={() => {
                  setStatusFilter("");
                  setTypeFilter("");
                  setDeptFilter("");
                  setSearchQuery("");
                }}
                className="mt-3 text-xs"
              >
                Afficher tout l'existant
              </Button>
            )}
          </Empty>
        )}

        <div className="divide-y divide-neutral-100">
          {filtered.map((app) => {
            const ai = app.ai_evaluation;

            return (
              <div
                key={app.id}
                className="py-3.5 px-2 hover:bg-neutral-50/80 rounded transition-colors flex flex-col md:flex-row items-start md:items-center justify-between gap-3"
              >
                <div className="min-w-0 space-y-1 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-bold text-neutral-950 text-sm">{app.farmer_name}</span>
                    <a
                      href={`tel:${app.farmer_phone}`}
                      className="text-xs font-bold text-emerald-800 hover:underline"
                    >
                      {app.farmer_phone}
                    </a>
                    {getTypeBadge(app.offer_type)}
                    {getStatusBadge(app.status)}
                  </div>

                  <p className="text-xs text-neutral-700">
                    <span className="font-semibold">{app.offer_title}</span> · Sollicite{" "}
                    <strong>{formatFcfa(app.amount_requested)}</strong> pour {app.crop_type} ({app.surface_ha} ha)
                  </p>

                  <div className="flex items-center gap-3 text-xs text-neutral-500">
                    <span>📍 {app.commune}, {app.department}</span>
                    <span>· Date : {formatDate(app.created_at)}</span>
                    {app.amount_approved && (
                      <span className="text-emerald-700 font-bold">
                        · Accordé : {formatFcfa(app.amount_approved)}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0 self-end md:self-center">
                  {ai && (
                    <div className="text-right">
                      <div className="flex items-center gap-1.5 justify-end">
                        <span className="text-xs font-bold text-neutral-900">{ai.score}/100</span>
                        {getVerdictBadge(ai.verdict)}
                      </div>
                      <span className="text-[10px] text-neutral-500">Avis IA automatique</span>
                    </div>
                  )}

                  <Button
                    variant="primary"
                    onClick={() => onReview(app)}
                    className="h-8 px-3 text-xs font-bold"
                  >
                    Instruire <ArrowRight className="w-3.5 h-3.5 ml-1" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

// ============================================================================
// COMPOSANT : Modal d'instruction et décision (Agent)
// ============================================================================

function ReviewApplicationModal({
  application,
  onClose,
  onSuccess,
}: {
  application: FinancialApplication;
  onClose: () => void;
  onSuccess: (updated: FinancialApplication) => void;
}) {
  const [activeTab, setActiveTab] = useState<"project" | "ai" | "decision">("ai");
  const [decisionStatus, setDecisionStatus] = useState<"approuve" | "rejete">("approuve");
  const [amountApproved, setAmountApproved] = useState<number>(
    application.amount_approved || application.ai_evaluation?.recommended_amount || application.amount_requested
  );
  const [interestApproved, setInterestApproved] = useState<number>(3.5);
  const [durationApproved, setDurationApproved] = useState<number>(12);
  const [conditionsText, setConditionsText] = useState<string>(
    application.ai_evaluation?.recommended_conditions?.join("\n") || ""
  );
  const [notes, setNotes] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");

  // Re-eval AI mutation
  const reevalMutation = useMutation({
    mutationFn: () => {
      return fetchWithAuth<FinancialApplication>(`/api/v1/finance/applications/${application.id}/evaluate-ai`, {
        method: "POST",
      });
    },
    onSuccess: (updated) => {
      onSuccess(updated);
    },
  });

  // Decision mutation
  const decisionMutation = useMutation({
    mutationFn: () => {
      if (!notes.trim()) {
        throw new Error("Veuillez saisir une motivation ou compte-rendu pour motiver votre décision officielle.");
      }

      const conditionsList = conditionsText
        .split("\n")
        .map((c) => c.trim())
        .filter(Boolean);

      return fetchWithAuth<FinancialApplication>(`/api/v1/finance/applications/${application.id}/decision`, {
        method: "PATCH",
        body: JSON.stringify({
          status: decisionStatus,
          amount_approved: decisionStatus === "approuve" ? Number(amountApproved) : null,
          interest_rate_approved: decisionStatus === "approuve" ? Number(interestApproved) : null,
          duration_approved_months: decisionStatus === "approuve" ? Number(durationApproved) : null,
          conditions: conditionsList,
          motivation_or_notes: notes,
        }),
      });
    },
    onSuccess: (updated) => {
      onSuccess(updated);
    },
    onError: (err: any) => {
      setErrorMsg(err.message || "Erreur lors de l'enregistrement de la décision.");
    },
  });

  // Disburse mutation
  const disburseMutation = useMutation({
    mutationFn: () => {
      return fetchWithAuth<FinancialApplication>(`/api/v1/finance/applications/${application.id}/disburse`, {
        method: "PATCH",
        body: JSON.stringify({
          contract_ref: `AGRI-${application.offer_type.toUpperCase()}-${application.id.slice(-6).toUpperCase()}`,
          payment_reference: `VIR-${Date.now().toString().slice(-6)}`,
          notes: "Déboursement validé après conformité du dossier.",
        }),
      });
    },
    onSuccess: (updated) => {
      onSuccess(updated);
    },
  });

  const ai = application.ai_evaluation;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl max-w-3xl w-full p-5 sm:p-6 space-y-4 shadow-xl border border-neutral-200 my-8">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-neutral-100 pb-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-bold text-lg text-neutral-950">{application.farmer_name}</span>
              {getTypeBadge(application.offer_type)}
              {getStatusBadge(application.status)}
            </div>
            <p className="text-xs text-neutral-500">
              NPI : {application.farmer_npi} · Tél : {application.farmer_phone} · {application.commune} ({application.department})
            </p>
          </div>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        {errorMsg && <Alert tone="error">{errorMsg}</Alert>}

        {/* Onglets internes */}
        <div className="flex items-center gap-2 border-b border-neutral-200 pb-2">
          <button
            onClick={() => setActiveTab("ai")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
              activeTab === "ai"
                ? "bg-purple-100 text-purple-900 border border-purple-300"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-purple-700" />
            Analyse & Risque IA ({ai?.score || 0}/100)
          </button>
          <button
            onClick={() => setActiveTab("project")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
              activeTab === "project"
                ? "bg-emerald-100 text-emerald-900 border border-emerald-300"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            <FileText className="w-3.5 h-3.5 text-emerald-700" />
            Détail du projet & Exploitation
          </button>
          <button
            onClick={() => setActiveTab("decision")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
              activeTab === "decision"
                ? "bg-blue-100 text-blue-900 border border-blue-300"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-blue-700" />
            Formulaire de Décision Officielle
          </button>
        </div>

        {/* CONTENU ONGLETS */}

        {/* 1. ANALYSE IA */}
        {activeTab === "ai" && (
          <div className="space-y-3.5 text-xs">
            {ai ? (
              <>
                <div className="p-3.5 rounded-xl bg-purple-50/70 border border-purple-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <span className="text-[11px] font-bold text-purple-800 uppercase tracking-wider block">
                      Score de solvabilité & viabilité agronomique
                    </span>
                    <div className="text-2xl font-black text-purple-950 mt-0.5">
                      {ai.score} <span className="text-sm font-normal text-purple-700">/ 100</span>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    {getVerdictBadge(ai.verdict)}
                    <span className="text-[11px] text-neutral-500">
                      Montant suggéré par l'IA : <strong>{formatFcfa(ai.recommended_amount)}</strong>
                    </span>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-neutral-50 border border-neutral-200">
                  <span className="font-bold text-neutral-900 block mb-1">Synthèse exécutive :</span>
                  <p className="text-neutral-700 leading-relaxed">{ai.summary}</p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-emerald-50/60 border border-emerald-200 space-y-1.5">
                    <span className="font-bold text-emerald-950 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-700" /> Forces identifiées
                    </span>
                    <ul className="list-disc pl-4 space-y-1 text-emerald-900">
                      {ai.strengths.map((s, idx) => (
                        <li key={idx}>{s}</li>
                      ))}
                    </ul>
                  </div>

                  <div className="p-3 rounded-lg bg-amber-50/60 border border-amber-200 space-y-1.5">
                    <span className="font-bold text-amber-950 flex items-center gap-1">
                      <AlertOctagon className="w-3.5 h-3.5 text-amber-700" /> Risques & Vigilance
                    </span>
                    <ul className="list-disc pl-4 space-y-1 text-amber-900">
                      {ai.risks.map((r, idx) => (
                        <li key={idx}>{r}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                {ai.recommended_conditions?.length > 0 && (
                  <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-950 space-y-1">
                    <span className="font-bold block">Conditions suggérées pour l'accord :</span>
                    <ul className="list-disc pl-4 space-y-0.5">
                      {ai.recommended_conditions.map((c, idx) => (
                        <li key={idx}>{c}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="flex justify-end pt-1">
                  <Button
                    variant="outline"
                    onClick={() => reevalMutation.mutate()}
                    loading={reevalMutation.isPending}
                    className="text-xs"
                  >
                    <RefreshCw className="w-3.5 h-3.5 mr-1" /> Re-calculer l'analyse IA
                  </Button>
                </div>
              </>
            ) : (
              <Empty>
                <p className="text-xs text-neutral-500">Aucune évaluation IA disponible pour ce dossier.</p>
                <Button
                  variant="primary"
                  onClick={() => reevalMutation.mutate()}
                  loading={reevalMutation.isPending}
                  className="mt-2 text-xs"
                >
                  Générer l'analyse IA maintenant
                </Button>
              </Empty>
            )}
          </div>
        )}

        {/* 2. DÉTAIL DU PROJET */}
        {activeTab === "project" && (
          <div className="space-y-3.5 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-neutral-50 border border-neutral-200">
              <div>
                <span className="text-neutral-500 block">Offre postulée :</span>
                <span className="font-bold text-neutral-900">{application.offer_title}</span>
              </div>
              <div>
                <span className="text-neutral-500 block">Institution financière :</span>
                <span className="font-bold text-neutral-900">{application.offer_institution}</span>
              </div>
              <div>
                <span className="text-neutral-500 block">Montant sollicité :</span>
                <span className="font-bold text-neutral-900 text-sm">{formatFcfa(application.amount_requested)}</span>
              </div>
              <div>
                <span className="text-neutral-500 block">Culture & Surface :</span>
                <span className="font-bold text-neutral-900">{application.crop_type} ({application.surface_ha} ha)</span>
              </div>
              <div>
                <span className="text-neutral-500 block">Récolte estimée déclarée :</span>
                <span className="font-bold text-neutral-900">
                  {application.declared_harvest_estimate_kg ? `${application.declared_harvest_estimate_kg} kg` : "Non précisée"}
                </span>
              </div>
              <div>
                <span className="text-neutral-500 block">Parcelle déclarée :</span>
                <span className="font-bold text-neutral-900">{application.land_title || "Non rattachée"}</span>
              </div>
            </div>

            <div>
              <span className="font-bold text-neutral-700 block mb-1">Descriptif du projet :</span>
              <p className="p-3 rounded bg-white border border-neutral-200 leading-relaxed text-neutral-800">
                {application.project_description}
              </p>
            </div>

            {application.guarantees_or_notes && (
              <div>
                <span className="font-bold text-neutral-700 block mb-1">Garanties ou plan de remboursement :</span>
                <p className="p-3 rounded bg-white border border-neutral-200 leading-relaxed text-neutral-800">
                  {application.guarantees_or_notes}
                </p>
              </div>
            )}
          </div>
        )}

        {/* 3. FORMULAIRE DE DÉCISION */}
        {activeTab === "decision" && (
          <div className="space-y-3.5 text-xs">
            <div>
              <label className="block font-bold text-neutral-700 mb-1">Issue de la décision</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setDecisionStatus("approuve")}
                  className={`p-2.5 rounded-lg border font-bold text-center transition-all ${
                    decisionStatus === "approuve"
                      ? "bg-emerald-100 border-emerald-600 text-emerald-950 ring-2 ring-emerald-600"
                      : "bg-white border-neutral-200 text-neutral-700 hover:bg-neutral-50"
                  }`}
                >
                  ✅ Approuver le dossier
                </button>
                <button
                  type="button"
                  onClick={() => setDecisionStatus("rejete")}
                  className={`p-2.5 rounded-lg border font-bold text-center transition-all ${
                    decisionStatus === "rejete"
                      ? "bg-red-100 border-red-600 text-red-950 ring-2 ring-red-600"
                      : "bg-white border-neutral-200 text-neutral-700 hover:bg-neutral-50"
                  }`}
                >
                  ❌ Rejeter la demande
                </button>
              </div>
            </div>

            {decisionStatus === "approuve" && (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block font-bold text-neutral-700 mb-1">Montant validé (FCFA)</label>
                    <input
                      type="number"
                      value={amountApproved}
                      onChange={(e) => setAmountApproved(Number(e.target.value))}
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-neutral-700 mb-1">Taux / Prime validé (%)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={interestApproved}
                      onChange={(e) => setInterestApproved(Number(e.target.value))}
                      className={inputCls}
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-neutral-700 mb-1">Durée (mois)</label>
                    <input
                      type="number"
                      value={durationApproved}
                      onChange={(e) => setDurationApproved(Number(e.target.value))}
                      className={inputCls}
                    />
                  </div>
                </div>

                <div>
                  <label className="block font-bold text-neutral-700 mb-1">
                    Conditions obligatoires imposées (une par ligne)
                  </label>
                  <textarea
                    rows={3}
                    value={conditionsText}
                    onChange={(e) => setConditionsText(e.target.value)}
                    placeholder="Ex: Déblocage après constat de levée&#10;Contrôle phytosanitaire obligatoire&#10;Adhésion à la coopérative"
                    className={inputCls}
                  />
                </div>
              </>
            )}

            <div>
              <label className="block font-bold text-neutral-700 mb-1">
                Motivation officielle / Compte-rendu (transmis à l'exploitant) *
              </label>
              <textarea
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Précisez les motifs de validation ou de rejet qui seront notifiés au producteur..."
                className={inputCls}
              />
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-neutral-100">
              {application.status === "approuve" && (
                <Button
                  variant="soft"
                  onClick={() => disburseMutation.mutate()}
                  loading={disburseMutation.isPending}
                  className="text-xs"
                >
                  <Banknote className="w-3.5 h-3.5 mr-1" /> Marquer comme Déboursé / Actif
                </Button>
              )}

              <div className="flex items-center gap-2 ml-auto">
                <Button variant="outline" onClick={onClose} className="text-xs">
                  Fermer
                </Button>
                <Button
                  variant="primary"
                  onClick={() => decisionMutation.mutate()}
                  loading={decisionMutation.isPending}
                  className="text-xs font-bold"
                >
                  Enregistrer la décision
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
