import { API_ORIGIN, authStore, formatDate, formatRelative, speak, stopSpeaking, useSession } from "@agri/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  Clock,
  HeartPulse,
  Info,
  Phone,
  PhoneCall,
  Plus,
  Search,
  ShieldAlert,
  Stethoscope,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, CardHeader, Empty, Loading, Metric } from "../../components/ui";
import { DEPARTMENTS } from "../../lib/benin";

// --- Types ---

interface HealthRecommendation {
  urgency_level: "vitale" | "urgente" | "moderee" | "faible";
  urgency_label: string;
  category: "intoxication_pesticide" | "traumatisme_agricole" | "morsure_piqure" | "coup_chaleur_deshydratation" | "infectieux_paludisme" | "autre";
  category_label: string;
  first_aid_steps: string[];
  things_to_avoid?: string[];
  avoid?: string[];
  medical_orientation?: string;
  medical_referral?: string;
  simple_summary: string;
}

interface AssignedService {
  facility_name: string;
  facility_type: string;
  facility_phone?: string | null;
  department: string;
  commune?: string | null;
  intervention_type: string;
  instructions?: string | null;
  assigned_by: string;
  assigned_at: string;
}

interface HealthAlert {
  id: string;
  npi: string;
  patient_name: string;
  patient_relation: string;
  phone: string;
  department: string;
  commune: string;
  locality?: string | null;
  land_id?: string | null;
  symptoms: string;
  suspected_cause?: string | null;
  work_related: boolean;
  urgency_perceived: string;
  urgency_level: "vitale" | "urgente" | "moderee" | "faible";
  urgency_label: string;
  category: string;
  category_label: string;
  ai_recommendation?: HealthRecommendation | null;
  status: "signale" | "pris_en_charge" | "en_cours" | "resolu";
  assigned_service?: AssignedService | null;
  resolution_notes?: string | null;
  created_at: string;
  updated_at: string;
}

interface HealthStats {
  total_alerts: number;
  pending_alerts: number;
  in_treatment_alerts?: number;
  assigned_alerts?: number;
  in_progress_alerts?: number;
  resolved_alerts: number;
  vital_urgencies?: number;
  vital_alerts?: number;
  by_category: Record<string, number>;
  by_department: Record<string, number>;
  by_urgency: Record<string, number>;
  recent_hotspots?: Array<{
    id: string;
    department: string;
    commune: string;
    category_label: string;
    patient_name: string;
    created_at: string;
    status: string;
  }>;
  recent_vital_hotspots?: Array<any>;
}

interface HealthFacility {
  name: string;
  department: string;
  commune: string;
  phone: string;
  type: string;
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

const inputCls = "w-full px-3 py-2 text-sm border border-neutral-300 rounded focus:border-emerald-800 focus:ring-1 focus:ring-emerald-800 focus:outline-none bg-white";

const SYMPTOM_PRESETS = [
  { label: "🐍 Morsure de serpent", text: "Morsure de serpent à la cheville/main survenue au champ, douleur vive et gonflement rapide." },
  { label: "☠️ Intoxication pesticide", text: "Vertiges, nausées, vomissements et difficultés respiratoires après pulvérisation de pesticides." },
  { label: "🩸 Coupure d'outil / Machette", text: "Plaie profonde avec saignement abondant causée par un coupe-coupe ou lame agricole." },
  { label: "☀️ Coup de chaleur", text: "Malaise, vertiges, transpiration excessive et confusion mentale après exposition prolongée au soleil." },
  { label: "🌡️ Forte fièvre / Paludisme", text: "Forte fièvre soudaine, frissons intenses, courbatures et maux de tête sévères." },
  { label: "🚜 Chute d'engin / Traumatisme", text: "Chute d'une remorque ou tracteur avec douleur aiguë et impossibilité de bouger le membre." },
];

export function HealthPage() {
  const { user } = useSession();
  const queryClient = useQueryClient();
  const isAgent = user?.role === "state_agent" || user?.role === "state_supervisor";

  // Farmer state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<HealthAlert | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);

  // Agent state
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [urgencyFilter, setUrgencyFilter] = useState<string>("");
  const [deptFilter, setDeptFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [assigningAlert, setAssigningAlert] = useState<HealthAlert | null>(null);
  const [statusUpdateAlert, setStatusUpdateAlert] = useState<HealthAlert | null>(null);

  // Stop audio on unmount
  useEffect(() => {
    return () => stopSpeaking();
  }, []);

  // --- Queries ---

  // Farmer's own alerts
  const myAlertsQuery = useQuery({
    queryKey: ["farmer-health", "alerts", "me"],
    queryFn: () => fetchWithAuth<HealthAlert[]>("/api/v1/farmer-health/alerts/me"),
    enabled: !isAgent,
  });

  // Agent: all alerts
  const allAlertsQuery = useQuery({
    queryKey: ["farmer-health", "alerts", statusFilter, urgencyFilter, deptFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (urgencyFilter) params.set("urgency", urgencyFilter);
      if (deptFilter) params.set("department", deptFilter);
      return fetchWithAuth<HealthAlert[]>(`/api/v1/farmer-health/alerts?${params.toString()}`);
    },
    enabled: isAgent,
  });

  // Agent: stats
  const statsQuery = useQuery({
    queryKey: ["farmer-health", "stats"],
    queryFn: () => fetchWithAuth<HealthStats>("/api/v1/farmer-health/stats"),
    enabled: isAgent,
  });

  // Pre-seeded Benin facilities
  const facilitiesQuery = useQuery({
    queryKey: ["farmer-health", "facilities"],
    queryFn: () => fetchWithAuth<HealthFacility[]>("/api/v1/farmer-health/facilities"),
  });

  // --- Audio TTS player helper ---
  const playAlertVoice = (alert: HealthAlert) => {
    if (isPlayingAudio) {
      stopSpeaking();
      setIsPlayingAudio(false);
      return;
    }
    const rec = alert.ai_recommendation;
    if (!rec) return;

    const avoidList = rec.things_to_avoid || rec.avoid || [];
    const orientation = rec.medical_orientation || rec.medical_referral || "";

    const parts = [
      rec.simple_summary,
      rec.first_aid_steps?.length ? `Premiers secours : ${rec.first_aid_steps.join(". ")}` : "",
      avoidList.length ? `Attention, à éviter formellement : ${avoidList.join(". ")}` : "",
      orientation ? `Orientation médicale : ${orientation}` : "",
    ].filter(Boolean);

    const textToSpeak = parts.join(". ");
    setIsPlayingAudio(true);
    speak(textToSpeak, "fr-FR", () => setIsPlayingAudio(false));
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* En-tête de la page */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-neutral-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-lg bg-red-100 text-red-700">
              <HeartPulse className="w-6 h-6" />
            </span>
            <div>
              <h1 className="text-xl sm:text-2xl font-black text-neutral-950">
                Santé des Exploitants & Premiers Secours
              </h1>
              <p className="text-xs sm:text-sm text-neutral-600">
                {isAgent
                  ? "Cockpit de coordination médicale et gestion des urgences sanitaires en milieu rural."
                  : "Assistance médicale d'urgence IA et orientation vers les centres de santé au Bénin."}
              </p>
            </div>
          </div>
        </div>

        {!isAgent && (
          <Button
            variant="primary"
            onClick={() => setShowCreateModal(true)}
            className="bg-red-600 hover:bg-red-700 text-white font-bold border-red-700 shadow-sm"
          >
            <AlertTriangle className="w-4 h-4 text-white" />
            Signaler une urgence / problème de santé
          </Button>
        )}
      </div>

      {/* VUE AGENT / SUPERVISEUR */}
      {isAgent && (
        <AgentHealthCockpit
          stats={statsQuery.data}
          alerts={allAlertsQuery.data || []}
          isLoading={allAlertsQuery.isLoading || statsQuery.isLoading}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          urgencyFilter={urgencyFilter}
          setUrgencyFilter={setUrgencyFilter}
          deptFilter={deptFilter}
          setDeptFilter={setDeptFilter}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          onSelectAlert={(a) => setSelectedAlert(a)}
          onAssign={(a) => setAssigningAlert(a)}
          onUpdateStatus={(a) => setStatusUpdateAlert(a)}
        />
      )}

      {/* VUE EXPLOITANT AGRICOLE */}
      {!isAgent && (
        <FarmerHealthView
          alerts={myAlertsQuery.data || []}
          isLoading={myAlertsQuery.isLoading}
          onNewAlert={() => setShowCreateModal(true)}
          onViewDetails={(a) => setSelectedAlert(a)}
          onPlayAudio={playAlertVoice}
          isPlayingAudio={isPlayingAudio}
        />
      )}

      {/* MODAL : Déclarer une nouvelle alerte (Exploitant) */}
      {showCreateModal && (
        <CreateAlertModal
          onClose={() => setShowCreateModal(false)}
          onCreated={(newAlert) => {
            setShowCreateModal(false);
            setSelectedAlert(newAlert);
            queryClient.invalidateQueries({ queryKey: ["farmer-health"] });
          }}
        />
      )}

      {/* MODAL : Détail de l'alerte & Recommandations IA */}
      {selectedAlert && (
        <AlertDetailModal
          alert={selectedAlert}
          isAgent={Boolean(isAgent)}
          onClose={() => {
            setSelectedAlert(null);
            stopSpeaking();
            setIsPlayingAudio(false);
          }}
          onPlayVoice={() => playAlertVoice(selectedAlert)}
          isPlayingAudio={isPlayingAudio}
          onAssign={isAgent ? () => setAssigningAlert(selectedAlert) : undefined}
          onUpdateStatus={isAgent ? () => setStatusUpdateAlert(selectedAlert) : undefined}
        />
      )}

      {/* MODAL : Assigner un service de santé (Agent) */}
      {assigningAlert && (
        <AssignServiceModal
          alert={assigningAlert}
          facilities={facilitiesQuery.data || []}
          onClose={() => setAssigningAlert(null)}
          onSuccess={(updated) => {
            setAssigningAlert(null);
            if (selectedAlert?.id === updated.id) setSelectedAlert(updated);
            queryClient.invalidateQueries({ queryKey: ["farmer-health"] });
          }}
        />
      )}

      {/* MODAL : Mettre à jour le statut (Agent) */}
      {statusUpdateAlert && (
        <UpdateStatusModal
          alert={statusUpdateAlert}
          onClose={() => setStatusUpdateAlert(null)}
          onSuccess={(updated) => {
            setStatusUpdateAlert(null);
            if (selectedAlert?.id === updated.id) setSelectedAlert(updated);
            queryClient.invalidateQueries({ queryKey: ["farmer-health"] });
          }}
        />
      )}
    </div>
  );
}

// ============================================================================
// COMPOSANT : Vue Exploitant
// ============================================================================

function FarmerHealthView({
  alerts,
  isLoading,
  onNewAlert,
  onViewDetails,
  onPlayAudio,
  isPlayingAudio,
}: {
  alerts: HealthAlert[];
  isLoading: boolean;
  onNewAlert: () => void;
  onViewDetails: (alert: HealthAlert) => void;
  onPlayAudio: (alert: HealthAlert) => void;
  isPlayingAudio: boolean;
}) {
  const latestAlert = alerts[0];

  return (
    <div className="space-y-6">
      {/* Bannière d'alerte / Action rapide */}
      <div className="p-4 sm:p-5 rounded-xl border border-red-200 bg-gradient-to-r from-red-50 to-amber-50 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="space-y-1 max-w-2xl">
          <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-black bg-red-600 text-white uppercase tracking-wider">
            <ShieldAlert className="w-3.5 h-3.5" /> Urgences au champ
          </div>
          <h2 className="text-base sm:text-lg font-bold text-neutral-900">
            Une morsure, une intoxication pesticide ou une blessure ?
          </h2>
          <p className="text-xs sm:text-sm text-neutral-700 leading-relaxed">
            Ne perdez pas de temps : signalez immédiatement la situation. L'IA génère les gestes de premiers secours immédiats
            et nos agents territoriaux coordonnent votre prise en charge médicale.
          </p>
        </div>
        <Button
          variant="primary"
          onClick={onNewAlert}
          className="bg-red-600 hover:bg-red-700 text-white font-bold shrink-0 border-red-700 shadow-sm"
        >
          <AlertOctagon className="w-4 h-4 mr-1 text-white" />
          Déclarer un problème
        </Button>
      </div>

      {/* Dernier signalement actif avec recommandations */}
      {latestAlert && (
        <Card className="border-emerald-300 bg-white">
          <CardHeader
            icon={HeartPulse}
            title="Dernier signalement enregistré"
            action={
              <Badge tone={getStatusTone(latestAlert.status)}>
                {getStatusLabel(latestAlert.status)}
              </Badge>
            }
          />
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 p-3 rounded-lg bg-neutral-50 border border-neutral-200 text-xs sm:text-sm">
              <div>
                <span className="font-bold text-neutral-900">{latestAlert.patient_name}</span> ({latestAlert.patient_relation}) ·{" "}
                <span className="text-neutral-600">{latestAlert.commune}, {latestAlert.department}</span>
              </div>
              <div className="flex items-center gap-2">
                <UrgencyBadge level={latestAlert.urgency_level} label={latestAlert.urgency_label} />
                <span className="text-neutral-500 tabular-nums">{formatRelative(latestAlert.created_at)}</span>
              </div>
            </div>

            {/* Service médical affecté */}
            {latestAlert.assigned_service ? (
              <div className="p-3.5 rounded-lg border border-blue-200 bg-blue-50/70 text-blue-950 space-y-2">
                <div className="flex items-center justify-between gap-2 font-bold text-sm">
                  <span className="flex items-center gap-2">
                    <Building2 className="w-4 h-4 text-blue-700" />
                    Centre de santé affecté : {latestAlert.assigned_service.facility_name}
                  </span>
                  {latestAlert.assigned_service.facility_phone && (
                    <a
                      href={`tel:${latestAlert.assigned_service.facility_phone}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded bg-blue-700 text-white text-xs font-bold hover:bg-blue-800 transition-colors"
                    >
                      <PhoneCall className="w-3.5 h-3.5" />
                      Appeler : {latestAlert.assigned_service.facility_phone}
                    </a>
                  )}
                </div>
                {latestAlert.assigned_service.instructions && (
                  <p className="text-xs text-blue-900">
                    <span className="font-semibold">Consignes de l'agent :</span> {latestAlert.assigned_service.instructions}
                  </p>
                )}
              </div>
            ) : (
              <div className="p-3 rounded-lg border border-amber-200 bg-amber-50 text-amber-950 text-xs flex items-center gap-2">
                <Clock className="w-4 h-4 text-amber-700 shrink-0" />
                <span>Votre alerte est enregistrée. Un agent territorial est notifié pour coordonner un centre de santé proche.</span>
              </div>
            )}

            {/* Recommandations IA immédiates */}
            {latestAlert.ai_recommendation && (
              <div className="space-y-3 pt-2 border-t border-neutral-100">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-bold text-neutral-900 flex items-center gap-2">
                    <Stethoscope className="w-4 h-4 text-emerald-800" />
                    Consignes d'urgence IA (Premiers secours)
                  </h3>
                  <button
                    type="button"
                    onClick={() => onPlayAudio(latestAlert)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-bold bg-neutral-100 hover:bg-neutral-200 text-neutral-800 transition-colors cursor-pointer"
                  >
                    {isPlayingAudio ? (
                      <>
                        <VolumeX className="w-3.5 h-3.5 text-red-600" /> Arrêter la voix
                      </>
                    ) : (
                      <>
                        <Volume2 className="w-3.5 h-3.5 text-emerald-800" /> Écouter les consignes
                      </>
                    )}
                  </button>
                </div>

                <div className="p-3 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs sm:text-sm text-emerald-950">
                  <p className="font-semibold">{latestAlert.ai_recommendation.simple_summary}</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-neutral-50 border border-neutral-200">
                    <h4 className="text-xs font-bold text-neutral-900 mb-2 flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-700" />
                      Gestes immédiats à faire
                    </h4>
                    <ul className="space-y-1.5 text-xs text-neutral-700 list-disc pl-4">
                      {latestAlert.ai_recommendation.first_aid_steps.map((s, idx) => (
                        <li key={idx}>{s}</li>
                      ))}
                    </ul>
                  </div>

                  <div className="p-3 rounded-lg bg-red-50 border border-red-200">
                    <h4 className="text-xs font-bold text-red-900 mb-2 flex items-center gap-1.5">
                      <AlertOctagon className="w-3.5 h-3.5 text-red-700" />
                      À ÉVITER ABSOLUMENT
                    </h4>
                    <ul className="space-y-1.5 text-xs text-red-900 list-disc pl-4">
                      {(latestAlert.ai_recommendation.things_to_avoid || latestAlert.ai_recommendation.avoid || []).map((a, idx) => (
                        <li key={idx}>{a}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="text-xs text-neutral-600">
                  <span className="font-bold text-neutral-900">Orientation médicale :</span>{" "}
                  {latestAlert.ai_recommendation.medical_orientation || latestAlert.ai_recommendation.medical_referral}
                </div>
              </div>
            )}

            <div className="flex justify-end pt-2">
              <Button variant="outline" onClick={() => onViewDetails(latestAlert)} className="text-xs">
                Voir la fiche complète
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Historique complet des signalements */}
      <Card>
        <CardHeader
          icon={HeartPulse}
          title={`Mes signalements de santé (${alerts.length})`}
          action={
            <Button variant="ghost" onClick={onNewAlert} className="text-xs">
              <Plus className="w-3.5 h-3.5 mr-1" /> Nouveau
            </Button>
          }
        />

        {isLoading && <Loading label="Chargement de vos signalements..." />}

        {!isLoading && alerts.length === 0 && (
          <Empty>
            <p className="font-semibold text-neutral-800">Aucun signalement de santé enregistré.</p>
            <p className="text-xs text-neutral-500 mt-1">
              En cas d'incident ou de malaise lors de vos travaux agricoles, utilisez le bouton ci-dessus pour obtenir de l'aide.
            </p>
          </Empty>
        )}

        <div className="space-y-2.5">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              onClick={() => onViewDetails(alert)}
              className="p-3.5 rounded-lg border border-neutral-200 hover:border-emerald-700 bg-white transition-all cursor-pointer flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
            >
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-sm text-neutral-900">{alert.patient_name}</span>
                  <Badge tone={getStatusTone(alert.status)}>{getStatusLabel(alert.status)}</Badge>
                  <UrgencyBadge level={alert.urgency_level} label={alert.urgency_label} />
                  <span className="text-xs text-neutral-500">{alert.category_label}</span>
                </div>
                <p className="text-xs text-neutral-600 truncate max-w-xl">
                  {alert.symptoms}
                </p>
                <div className="text-xs text-neutral-400">
                  {alert.commune}, {alert.department} · {formatDate(alert.created_at)}
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                {alert.assigned_service && (
                  <span className="text-xs text-blue-800 font-semibold bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                    🏥 {alert.assigned_service.facility_name.split("(")[0]}
                  </span>
                )}
                <Button variant="ghost" className="h-8 px-2 text-xs">
                  Détails <ArrowRight className="w-3.5 h-3.5 ml-1" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ============================================================================
// COMPOSANT : Vue Cockpit Agent & Superviseur
// ============================================================================

function AgentHealthCockpit({
  stats,
  alerts,
  isLoading,
  statusFilter,
  setStatusFilter,
  urgencyFilter,
  setUrgencyFilter,
  deptFilter,
  setDeptFilter,
  searchQuery,
  setSearchQuery,
  onSelectAlert,
  onAssign,
  onUpdateStatus,
}: {
  stats?: HealthStats;
  alerts: HealthAlert[];
  isLoading: boolean;
  statusFilter: string;
  setStatusFilter: (v: string) => void;
  urgencyFilter: string;
  setUrgencyFilter: (v: string) => void;
  deptFilter: string;
  setDeptFilter: (v: string) => void;
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  onSelectAlert: (a: HealthAlert) => void;
  onAssign: (a: HealthAlert) => void;
  onUpdateStatus: (a: HealthAlert) => void;
}) {
  const filteredAlerts = useMemo(() => {
    return alerts.filter((a) => {
      if (!searchQuery) return true;
      const q = searchQuery.toLowerCase();
      return (
        a.patient_name.toLowerCase().includes(q) ||
        a.phone.toLowerCase().includes(q) ||
        a.commune.toLowerCase().includes(q) ||
        a.symptoms.toLowerCase().includes(q)
      );
    });
  }, [alerts, searchQuery]);

  return (
    <div className="space-y-6">
      {/* Cartes de synthèse KPIs */}
      {stats && (() => {
        const vitalCount = stats.vital_urgencies ?? stats.vital_alerts ?? 0;
        const pendingCount = stats.pending_alerts ?? 0;
        const inTreatmentCount = stats.in_treatment_alerts ?? ((stats.assigned_alerts ?? 0) + (stats.in_progress_alerts ?? 0));
        const resolvedCount = stats.resolved_alerts ?? 0;
        const hotspots = stats.recent_hotspots ?? stats.recent_vital_hotspots ?? [];

        return (
          <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Card className="p-3.5 bg-neutral-50">
                <Metric label="Total alertes" value={stats.total_alerts} hint="Dossiers enregistrés" />
              </Card>
              <Card className={`p-3.5 ${vitalCount > 0 ? "bg-red-50 border-red-300" : "bg-neutral-50"}`}>
                <Metric
                  label="Urgences vitales"
                  value={vitalCount}
                  hint="Pronostic engagé"
                  hintTone={vitalCount > 0 ? "amber" : "neutral"}
                />
              </Card>
              <Card className={`p-3.5 ${pendingCount > 0 ? "bg-amber-50 border-amber-300" : "bg-neutral-50"}`}>
                <Metric
                  label="En attente"
                  value={pendingCount}
                  hint="Non affectées"
                  hintTone={pendingCount > 0 ? "amber" : "neutral"}
                />
              </Card>
              <Card className="p-3.5 bg-blue-50/60 border-blue-200">
                <Metric
                  label="Prises en charge"
                  value={inTreatmentCount}
                  hint="Soins en cours"
                  hintTone="blue"
                />
              </Card>
              <Card className="p-3.5 bg-emerald-50/60 border-emerald-200">
                <Metric
                  label="Résolus"
                  value={resolvedCount}
                  hint="Soignés / Clôturés"
                  hintTone="green"
                />
              </Card>
            </div>

            {hotspots.length > 0 && (
              <div className="p-3.5 rounded-lg border border-red-300 bg-red-50 text-red-950 space-y-2">
                <div className="flex items-center gap-2 font-bold text-sm text-red-800">
                  <AlertOctagon className="w-4 h-4 text-red-600 animate-pulse" />
                  Alertes vitales non résolues nécessitant une intervention immédiate :
                </div>
                <div className="flex flex-wrap gap-2">
                  {hotspots.map((h: any) => (
                    <span
                      key={h.id}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-white border border-red-200 text-xs font-semibold text-neutral-900 shadow-sm"
                    >
                      <span className="w-2 h-2 rounded-full bg-red-600 animate-ping" />
                      {h.patient_name} ({h.commune}, {h.department}) · {h.category_label}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        );
      })()}

      {/* Filtres de recherche */}
      <Card className="p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="block text-xs font-semibold text-neutral-600 mb-1">Recherche</label>
            <div className="relative">
              <Search className="w-4 h-4 text-neutral-400 absolute left-2.5 top-2.5" />
              <input
                type="text"
                placeholder="Nom, téléphone, commune…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className={`${inputCls} pl-8`}
              />
            </div>
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

          <div>
            <label className="block text-xs font-semibold text-neutral-600 mb-1">Niveau d'urgence</label>
            <select
              value={urgencyFilter}
              onChange={(e) => setUrgencyFilter(e.target.value)}
              className={inputCls}
            >
              <option value="">Toutes les urgences</option>
              <option value="vitale">🔴 Vitale (Danger mortel)</option>
              <option value="urgente">🟠 Urgente</option>
              <option value="moderee">🟡 Modérée</option>
              <option value="faible">🟢 Faible</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-600 mb-1">Statut prise en charge</label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className={inputCls}
            >
              <option value="">Tous les statuts</option>
              <option value="signale">En attente (Non assigné)</option>
              <option value="pris_en_charge">Pris en charge</option>
              <option value="en_cours">Soins en cours</option>
              <option value="resolu">Résolu</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Liste des alertes pour les agents */}
      <Card>
        <CardHeader
          icon={Activity}
          title={`Alertes de santé enregistrées (${filteredAlerts.length})`}
        />

        {isLoading && <Loading label="Chargement des alertes sanitaires..." />}

        {!isLoading && filteredAlerts.length === 0 && (
          <Empty>
            <p className="font-semibold text-neutral-800">Aucune alerte trouvée avec les filtres sélectionnés.</p>
          </Empty>
        )}

        <div className="divide-y divide-neutral-100">
          {filteredAlerts.map((alert) => (
            <div
              key={alert.id}
              className="py-3.5 px-2 hover:bg-neutral-50/80 rounded transition-colors flex flex-col md:flex-row items-start md:items-center justify-between gap-3"
            >
              <div className="min-w-0 space-y-1.5 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold text-neutral-950 text-sm">{alert.patient_name}</span>
                  <a
                    href={`tel:${alert.phone}`}
                    className="inline-flex items-center gap-1 text-xs font-bold text-emerald-800 hover:underline"
                  >
                    <Phone className="w-3 h-3" /> {alert.phone}
                  </a>
                  <UrgencyBadge level={alert.urgency_level} label={alert.urgency_label} />
                  <Badge tone={getStatusTone(alert.status)}>{getStatusLabel(alert.status)}</Badge>
                  <span className="text-xs text-neutral-500 font-medium">{alert.category_label}</span>
                </div>

                <p className="text-xs text-neutral-700 line-clamp-2">
                  <span className="font-semibold">Symptômes :</span> {alert.symptoms}
                </p>

                <div className="flex flex-wrap items-center gap-x-3 text-xs text-neutral-500">
                  <span>📍 {alert.commune} ({alert.department}){alert.locality ? ` · ${alert.locality}` : ""}</span>
                  <span>🕒 {formatRelative(alert.created_at)}</span>
                  {alert.work_related && <span className="text-amber-800 font-medium">⚠️ Au champ</span>}
                </div>

                {alert.assigned_service && (
                  <div className="text-xs font-medium text-blue-900 bg-blue-50 px-2.5 py-1 rounded inline-flex items-center gap-1.5 border border-blue-200">
                    <Building2 className="w-3.5 h-3.5 text-blue-700" />
                    <span>Affecté à : <strong>{alert.assigned_service.facility_name}</strong></span>
                    {alert.assigned_service.facility_phone && (
                      <span>({alert.assigned_service.facility_phone})</span>
                    )}
                  </div>
                )}
              </div>

              {/* Actions agent */}
              <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
                <Button variant="outline" onClick={() => onSelectAlert(alert)} className="text-xs h-9 px-2.5">
                  Fiche & IA
                </Button>
                <Button
                  variant="soft"
                  onClick={() => onAssign(alert)}
                  className="text-xs h-9 px-2.5 bg-blue-50 border-blue-300 text-blue-950 hover:bg-blue-100"
                >
                  <Building2 className="w-3.5 h-3.5 mr-1" />
                  Assigner service
                </Button>
                <Button variant="outline" onClick={() => onUpdateStatus(alert)} className="text-xs h-9 px-2.5">
                  Statut
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ============================================================================
// COMPOSANT MODAL : Déclarer une nouvelle alerte de santé (Exploitant)
// ============================================================================

function CreateAlertModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (alert: HealthAlert) => void;
}) {
  const { user } = useSession();
  const [patientRelation, setPatientRelation] = useState("exploitant");
  const [patientName, setPatientName] = useState(user?.full_name || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [department, setDepartment] = useState(DEPARTMENTS[2]); // Atlantique par défaut
  const [commune, setCommune] = useState("");
  const [locality, setLocality] = useState("");
  const [workRelated, setWorkRelated] = useState(true);
  const [urgencyPerceived, setUrgencyPerceived] = useState("urgente");
  const [symptoms, setSymptoms] = useState("");
  const [suspectedCause, setSuspectedCause] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!symptoms.trim()) {
      setError("Veuillez décrire brièvement les symptômes ou l'incident.");
      return;
    }
    if (!phone.trim()) {
      setError("Veuillez indiquer un numéro de téléphone joignable.");
      return;
    }
    if (!commune.trim()) {
      setError("Veuillez indiquer la commune de survenue.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const payload = {
        patient_relation: patientRelation,
        patient_name: patientName || "Exploitant",
        phone,
        department,
        commune,
        locality: locality || null,
        work_related: workRelated,
        urgency_perceived: urgencyPerceived,
        symptoms,
        suspected_cause: suspectedCause || null,
      };

      const result = await fetchWithAuth<HealthAlert>("/api/v1/farmer-health/alerts", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      onCreated(result);
    } catch (err: any) {
      setError(err.message || "Erreur lors de l'enregistrement de l'alerte.");
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-neutral-950/60 backdrop-blur-xs overflow-y-auto">
      <div className="bg-white rounded-xl shadow-2xl border border-neutral-200 w-full max-w-2xl my-6 overflow-hidden">
        {/* En-tête */}
        <div className="bg-gradient-to-r from-red-600 to-red-700 text-white p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <HeartPulse className="w-5 h-5 text-white" />
            <h2 className="text-base font-bold">Signaler une urgence ou un problème de santé</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-white/20 text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Corps formulaire */}
        <form onSubmit={handleSubmit} className="p-4 sm:p-6 space-y-4">
          {error && <Alert tone="error">{error}</Alert>}

          {/* Boutons d'insertion rapide de symptômes */}
          <div>
            <label className="block text-xs font-bold text-neutral-800 mb-1.5">
              Cas fréquents (cliquez pour pré-remplir) :
            </label>
            <div className="flex flex-wrap gap-1.5">
              {SYMPTOM_PRESETS.map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    setSymptoms(p.text);
                    if (p.label.includes("pesticide")) setSuspectedCause("Pulvérisation de produit phytosanitaire");
                    if (p.label.includes("serpent")) setSuspectedCause("Morsure de reptile au champ");
                  }}
                  className="px-2.5 py-1 rounded text-xs bg-neutral-100 hover:bg-neutral-200 text-neutral-800 font-medium transition-colors cursor-pointer"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">Personne concernée</label>
              <select
                value={patientRelation}
                onChange={(e) => setPatientRelation(e.target.value)}
                className={inputCls}
              >
                <option value="exploitant">Moi-même (exploitant)</option>
                <option value="membre_famille">Membre de la famille / Conjoint / Enfant</option>
                <option value="ouvrier_agricole">Ouvrier agricole / Manœuvre</option>
                <option value="autre">Autre personne</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">Nom du patient</label>
              <input
                type="text"
                value={patientName}
                onChange={(e) => setPatientName(e.target.value)}
                placeholder="Nom et prénoms"
                className={inputCls}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">Téléphone de contact *</label>
              <input
                type="tel"
                required
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+229 97 00 00 00"
                className={inputCls}
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">Département *</label>
              <select
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className={inputCls}
              >
                {DEPARTMENTS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">Commune *</label>
              <input
                type="text"
                required
                value={commune}
                onChange={(e) => setCommune(e.target.value)}
                placeholder="Ex: Dangbo, Allada, Parakou"
                className={inputCls}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-700 mb-1">Village / Hameau / Précisions de localisation</label>
            <input
              type="text"
              value={locality}
              onChange={(e) => setLocality(e.target.value)}
              placeholder="Ex: Village Hêvié, à côté de la rizière"
              className={inputCls}
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-neutral-800 mb-1">
              Description détaillée des symptômes ou blessure *
            </label>
            <textarea
              required
              rows={3}
              value={symptoms}
              onChange={(e) => setSymptoms(e.target.value)}
              placeholder="Décrivez ce que ressent la personne (douleurs, vomissements, plaie, perte de conscience, etc.)"
              className={inputCls}
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-700 mb-1">Cause suspectée (optionnel)</label>
            <input
              type="text"
              value={suspectedCause}
              onChange={(e) => setSuspectedCause(e.target.value)}
              placeholder="Ex: Machette rouillée, herbicide non identifié, soleil brûlant"
              className={inputCls}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">Niveau d'urgence ressenti</label>
              <select
                value={urgencyPerceived}
                onChange={(e) => setUrgencyPerceived(e.target.value)}
                className={inputCls}
              >
                <option value="vitale">🔴 Vitale (Inconscience, étouffement, saignement incontrôlé)</option>
                <option value="urgente">🟠 Urgente (Forte douleur, nausées aiguës, plaie ouverte)</option>
                <option value="moderee">🟡 Modérée (Gêne importante mais stable)</option>
                <option value="faible">🟢 Faible (Conseils généraux)</option>
              </select>
            </div>

            <div className="flex items-center gap-2 pt-5">
              <label className="inline-flex items-center gap-2 cursor-pointer text-xs font-medium text-neutral-800">
                <input
                  type="checkbox"
                  checked={workRelated}
                  onChange={(e) => setWorkRelated(e.target.checked)}
                  className="rounded border-neutral-300 text-emerald-800 focus:ring-emerald-800 h-4 w-4"
                />
                L'accident s'est produit au cours de travaux agricoles
              </label>
            </div>
          </div>

          {/* Boutons d'action */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-neutral-200">
            <Button variant="outline" onClick={onClose} disabled={submitting}>
              Annuler
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={submitting}
              className="bg-red-600 hover:bg-red-700 text-white font-bold border-red-700"
            >
              {submitting ? "Analyse IA & Envoi en cours…" : "Envoyer & Obtenir les premiers secours"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================================================
// COMPOSANT MODAL : Détail & Recommandations IA complètes
// ============================================================================

function AlertDetailModal({
  alert,
  isAgent,
  onClose,
  onPlayVoice,
  isPlayingAudio,
  onAssign,
  onUpdateStatus,
}: {
  alert: HealthAlert;
  isAgent: boolean;
  onClose: () => void;
  onPlayVoice: () => void;
  isPlayingAudio: boolean;
  onAssign?: () => void;
  onUpdateStatus?: () => void;
}) {
  const rec = alert.ai_recommendation;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-neutral-950/60 backdrop-blur-xs overflow-y-auto">
      <div className="bg-white rounded-xl shadow-2xl border border-neutral-200 w-full max-w-2xl my-6 overflow-hidden">
        {/* En-tête */}
        <div className="bg-neutral-900 text-white p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <HeartPulse className="w-5 h-5 text-red-500" />
            <div>
              <h2 className="text-sm sm:text-base font-bold">
                Dossier Médical : {alert.patient_name}
              </h2>
              <p className="text-xs text-neutral-400">
                {alert.commune}, {alert.department} · {formatDate(alert.created_at)}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-white/20 text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-4 sm:p-6 space-y-5 max-h-[80vh] overflow-y-auto">
          {/* Statut & Urgence */}
          <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-neutral-50 rounded-lg border border-neutral-200">
            <div className="flex items-center gap-2">
              <UrgencyBadge level={alert.urgency_level} label={alert.urgency_label} />
              <Badge tone={getStatusTone(alert.status)}>{getStatusLabel(alert.status)}</Badge>
            </div>
            <a
              href={`tel:${alert.phone}`}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded bg-emerald-800 text-white text-xs font-bold hover:bg-emerald-900"
            >
              <PhoneCall className="w-3.5 h-3.5" /> Joindre : {alert.phone}
            </a>
          </div>

          {/* Description des symptômes */}
          <div className="space-y-1">
            <h3 className="text-xs font-bold text-neutral-700 uppercase tracking-wider">Symptômes déclarés</h3>
            <p className="text-sm text-neutral-900 bg-neutral-50 p-3 rounded border border-neutral-200 leading-relaxed">
              {alert.symptoms}
            </p>
            {alert.suspected_cause && (
              <p className="text-xs text-neutral-500">
                <span className="font-semibold">Cause suspectée :</span> {alert.suspected_cause}
              </p>
            )}
          </div>

          {/* Structure assignée */}
          {alert.assigned_service && (
            <div className="p-3.5 rounded-lg border border-blue-200 bg-blue-50/70 text-blue-950 space-y-1.5">
              <div className="flex items-center justify-between gap-2 font-bold text-sm">
                <span className="flex items-center gap-1.5">
                  <Building2 className="w-4 h-4 text-blue-700" />
                  Service de santé : {alert.assigned_service.facility_name}
                </span>
                {alert.assigned_service.facility_phone && (
                  <a
                    href={`tel:${alert.assigned_service.facility_phone}`}
                    className="text-xs text-blue-800 underline font-bold"
                  >
                    📞 {alert.assigned_service.facility_phone}
                  </a>
                )}
              </div>
              <p className="text-xs text-blue-900">
                <span className="font-semibold">Type d'intervention :</span> {alert.assigned_service.intervention_type}
              </p>
              {alert.assigned_service.instructions && (
                <p className="text-xs text-blue-900">
                  <span className="font-semibold">Consignes :</span> {alert.assigned_service.instructions}
                </p>
              )}
            </div>
          )}

          {/* Recommandations IA */}
          {rec && (
            <div className="space-y-3 pt-3 border-t border-neutral-200">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-bold text-neutral-950 flex items-center gap-1.5">
                  <Stethoscope className="w-4 h-4 text-emerald-800" />
                  Recommandations médicales immédiates de l'IA
                </h3>
                <button
                  type="button"
                  onClick={onPlayVoice}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-bold bg-neutral-100 hover:bg-neutral-200 text-neutral-800 transition-colors"
                >
                  {isPlayingAudio ? (
                    <>
                      <VolumeX className="w-3.5 h-3.5 text-red-600" /> Arrêter la voix
                    </>
                  ) : (
                    <>
                      <Volume2 className="w-3.5 h-3.5 text-emerald-800" /> Écouter les consignes
                    </>
                  )}
                </button>
              </div>

              <div className="p-3 bg-emerald-50 border border-emerald-200 rounded text-xs sm:text-sm text-emerald-950">
                <p className="font-semibold">{rec.simple_summary}</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="p-3 rounded bg-neutral-50 border border-neutral-200">
                  <h4 className="text-xs font-bold text-emerald-900 mb-2 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-700" />
                    Premiers secours immédiats
                  </h4>
                  <ul className="space-y-1.5 text-xs text-neutral-800 list-disc pl-4">
                    {rec.first_aid_steps.map((step, idx) => (
                      <li key={idx}>{step}</li>
                    ))}
                  </ul>
                </div>

                <div className="p-3 rounded bg-red-50 border border-red-200">
                  <h4 className="text-xs font-bold text-red-900 mb-2 flex items-center gap-1">
                    <AlertOctagon className="w-3.5 h-3.5 text-red-700" />
                    À ÉVITER ABSOLUMENT
                  </h4>
                  <ul className="space-y-1.5 text-xs text-red-950 list-disc pl-4">
                    {(rec.things_to_avoid || rec.avoid || []).map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="p-3 rounded bg-neutral-50 border border-neutral-200 text-xs">
                <span className="font-bold text-neutral-900">Orientation sanitaire :</span>{" "}
                {rec.medical_orientation || rec.medical_referral}
              </div>
            </div>
          )}

          {/* Notes de résolution */}
          {alert.resolution_notes && (
            <div className="p-3 rounded bg-neutral-50 border border-neutral-200 text-xs text-neutral-700 space-y-1">
              <span className="font-bold text-neutral-900">Compte-rendu médical / Résolution :</span>
              <p>{alert.resolution_notes}</p>
            </div>
          )}

          {/* Actions spécifiques agent */}
          {isAgent && (
            <div className="flex flex-wrap items-center justify-end gap-2 pt-3 border-t border-neutral-200">
              {onAssign && (
                <Button variant="soft" onClick={onAssign} className="text-xs bg-blue-50 border-blue-300 text-blue-950">
                  <Building2 className="w-3.5 h-3.5 mr-1" />
                  {alert.assigned_service ? "Modifier le service assigné" : "Assigner un service de santé"}
                </Button>
              )}
              {onUpdateStatus && (
                <Button variant="outline" onClick={onUpdateStatus} className="text-xs">
                  Mettre à jour le statut
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// COMPOSANT MODAL : Assigner un service de santé (Agent)
// ============================================================================

function AssignServiceModal({
  alert,
  facilities,
  onClose,
  onSuccess,
}: {
  alert: HealthAlert;
  facilities: HealthFacility[];
  onClose: () => void;
  onSuccess: (updated: HealthAlert) => void;
}) {
  // Pré-sélectionner les centres du même département
  const deptFacilities = facilities.filter(
    (f) => f.department.toLowerCase() === alert.department.toLowerCase()
  );
  const otherFacilities = facilities.filter(
    (f) => f.department.toLowerCase() !== alert.department.toLowerCase()
  );

  const [selectedFacilityName, setSelectedFacilityName] = useState(
    deptFacilities[0]?.name || "Autre centre personnalisé"
  );
  const [customName, setCustomName] = useState("");
  const [phone, setPhone] = useState(deptFacilities[0]?.phone || "");
  const [facilityType, setFacilityType] = useState(deptFacilities[0]?.type || "centre_de_sante");
  const [interventionType, setInterventionType] = useState("consultation");
  const [instructions, setInstructions] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFacilitySelect = (name: string) => {
    setSelectedFacilityName(name);
    if (name === "custom") {
      setCustomName("");
      setPhone("");
      return;
    }
    const found = facilities.find((f) => f.name === name);
    if (found) {
      setPhone(found.phone);
      setFacilityType(found.type);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const finalFacilityName = selectedFacilityName === "custom" ? customName.trim() : selectedFacilityName;
    if (!finalFacilityName) {
      setError("Veuillez sélectionner ou saisir le nom du service de santé.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const payload = {
        facility_name: finalFacilityName,
        facility_type: facilityType,
        facility_phone: phone || null,
        department: alert.department,
        commune: alert.commune,
        intervention_type: interventionType,
        instructions: instructions || null,
      };

      const result = await fetchWithAuth<HealthAlert>(`/api/v1/farmer-health/alerts/${alert.id}/assign`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });

      onSuccess(result);
    } catch (err: any) {
      setError(err.message || "Erreur lors de l'assignation du service.");
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-neutral-950/60 backdrop-blur-xs overflow-y-auto">
      <div className="bg-white rounded-xl shadow-2xl border border-neutral-200 w-full max-w-lg my-6 overflow-hidden">
        <div className="bg-blue-800 text-white p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Building2 className="w-5 h-5 text-white" />
            <h2 className="text-sm sm:text-base font-bold">Assigner un service de santé</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-white/20 text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 sm:p-5 space-y-4">
          {error && <Alert tone="error">{error}</Alert>}

          <div className="p-3 rounded bg-neutral-50 border border-neutral-200 text-xs text-neutral-700">
            <span className="font-bold text-neutral-950">Patient :</span> {alert.patient_name} · {alert.phone}
            <br />
            <span className="font-bold text-neutral-950">Localisation :</span> {alert.commune} ({alert.department})
            <br />
            <span className="font-bold text-neutral-950">Urgence :</span> {alert.urgency_label}
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-700 mb-1">
              Structure de santé de référence
            </label>
            <select
              value={selectedFacilityName}
              onChange={(e) => handleFacilitySelect(e.target.value)}
              className={inputCls}
            >
              <optgroup label={`Département de ${alert.department}`}>
                {deptFacilities.map((f) => (
                  <option key={f.name} value={f.name}>
                    {f.name} ({f.commune})
                  </option>
                ))}
              </optgroup>
              <optgroup label="Autres départements / Centres nationaux">
                {otherFacilities.map((f) => (
                  <option key={f.name} value={f.name}>
                    {f.name} ({f.department})
                  </option>
                ))}
              </optgroup>
              <option value="custom">Autre structure (saisir manuellement)</option>
            </select>
          </div>

          {selectedFacilityName === "custom" && (
            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">Nom de la structure</label>
              <input
                type="text"
                required
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                placeholder="Ex: Dispensaire rural de Tori-Bossito"
                className={inputCls}
              />
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">Téléphone de la structure</label>
              <input
                type="text"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+229 21 00 00 00"
                className={inputCls}
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-neutral-700 mb-1">Mode d'intervention</label>
              <select
                value={interventionType}
                onChange={(e) => setInterventionType(e.target.value)}
                className={inputCls}
              >
                <option value="consultation">🏥 Prise en charge au Centre de Santé (CSA / Hôpital)</option>
                <option value="evacuation_urgence">🚑 Évacuation d'urgence / SAMU</option>
                <option value="soins_premiers_secours">🩹 Soins et premiers secours sur place</option>
                <option value="suivi_a_domicile">🚶 Visite d'un agent de santé communautaire</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-700 mb-1">
              Instructions ou consignes transmises à l'exploitant
            </label>
            <textarea
              rows={2}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="Ex: L'ambulance est en route. Gardez le patient au repos et ne tentez pas de le déplacer."
              className={inputCls}
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-neutral-200">
            <Button variant="outline" onClick={onClose} disabled={submitting}>
              Annuler
            </Button>
            <Button type="submit" variant="primary" disabled={submitting} className="bg-blue-700 hover:bg-blue-800 text-white font-bold">
              {submitting ? "Affectation en cours…" : "Confirmer l'affectation"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================================================
// COMPOSANT MODAL : Mettre à jour le statut de l'alerte (Agent)
// ============================================================================

function UpdateStatusModal({
  alert,
  onClose,
  onSuccess,
}: {
  alert: HealthAlert;
  onClose: () => void;
  onSuccess: (updated: HealthAlert) => void;
}) {
  const [status, setStatus] = useState<string>(alert.status);
  const [notes, setNotes] = useState<string>(alert.resolution_notes || "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const payload = {
        status,
        notes: notes || null,
      };

      const result = await fetchWithAuth<HealthAlert>(`/api/v1/farmer-health/alerts/${alert.id}/status`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });

      onSuccess(result);
    } catch (err: any) {
      setError(err.message || "Erreur lors de la mise à jour du statut.");
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-neutral-950/60 backdrop-blur-xs overflow-y-auto">
      <div className="bg-white rounded-xl shadow-2xl border border-neutral-200 w-full max-w-md my-6 overflow-hidden">
        <div className="bg-neutral-900 text-white p-4 flex items-center justify-between">
          <h2 className="text-sm sm:text-base font-bold">Mettre à jour le suivi de santé</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-white/20 text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 sm:p-5 space-y-4">
          {error && <Alert tone="error">{error}</Alert>}

          <div>
            <label className="block text-xs font-semibold text-neutral-700 mb-1">Nouveau statut</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className={inputCls}
            >
              <option value="signale">Signalé (En attente)</option>
              <option value="pris_en_charge">Pris en charge</option>
              <option value="en_cours">Soins en cours de traitement</option>
              <option value="resolu">Résolu / Patient rétabli</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-neutral-700 mb-1">
              Notes médicales d'évolution / Résolution
            </label>
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Ex: Patient reçu au CSA de Dangbo, perfusion administrée, état stabilisé."
              className={inputCls}
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-neutral-200">
            <Button variant="outline" onClick={onClose} disabled={submitting}>
              Annuler
            </Button>
            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? "Enregistrement…" : "Enregistrer"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================================================
// HELPERS D'AFFICHAGE & BADGES
// ============================================================================

function UrgencyBadge({ level, label }: { level: string; label: string }) {
  if (level === "vitale") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-black bg-red-600 text-white animate-pulse">
        <AlertOctagon className="w-3.5 h-3.5" /> {label}
      </span>
    );
  }
  if (level === "urgente") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold bg-amber-500 text-white">
        <AlertTriangle className="w-3.5 h-3.5" /> {label}
      </span>
    );
  }
  if (level === "moderee") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-900">
        <Info className="w-3.5 h-3.5" /> {label}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-neutral-100 text-neutral-700">
      {label}
    </span>
  );
}

function getStatusTone(status: string): "green" | "amber" | "blue" | "purple" | "neutral" {
  switch (status) {
    case "resolu":
      return "green";
    case "pris_en_charge":
      return "blue";
    case "en_cours":
      return "purple";
    case "signale":
    default:
      return "amber";
  }
}

function getStatusLabel(status: string): string {
  switch (status) {
    case "resolu":
      return "Résolu";
    case "pris_en_charge":
      return "Pris en charge";
    case "en_cours":
      return "En cours de soins";
    case "signale":
    default:
      return "En attente";
  }
}
