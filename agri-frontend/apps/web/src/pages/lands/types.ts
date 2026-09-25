import type { components } from "@agri/core";

export type PublicCall = components["schemas"]["PublicCallOut"];
export type AdminCall = components["schemas"]["CallOut"];
export type Application = components["schemas"]["ApplicationOut"];
export type Domain = components["schemas"]["DomainOut"];
export type PlanDoc = components["schemas"]["PlanOut"];
export type Plan = components["schemas"]["ValorizationPlan"];

export interface Eligibility { eligible: boolean; reasons: string[]; score: number; min_score: number; already_applied: boolean }

export interface Concession {
  id: string; call_id: string; domain_id: string; domain_name: string; department: string; commune: string; surface_hectares: number;
  farmer_name?: string | null; contract_type: string; duration_years: number; crop_type: string; planned_yield_kg: number; annual_fee_fcfa: number;
  mise_en_valeur_months: number; cahier_des_charges: string; status: "en_attente_acte" | "active" | "retiree" | "terminee" | "annulee";
  act_ref?: string | null; start_date?: string | null; end_date?: string | null; mise_en_valeur_deadline?: string | null;
  latest_mise_en_valeur_pct?: number | null; fees_due_fcfa: number; fees_paid_fcfa: number; balance_fcfa: number; mise_en_valeur_alert: boolean;
  reports?: { id: string; season: string; crop_type: string; area_cultivated_ha: number; actual_yield_kg: number; expected_yield_kg?: number }[];
  inspections?: { id: string; mise_en_valeur_pct: number; compliant: boolean; note: string; created_at: string }[];
  ai_review?: ConcessionReview;
}
export interface ConcessionReview { assessment: "conforme" | "a_surveiller" | "risque_de_defaut"; findings: string[]; early_warnings: string[]; recommended_actions: string[]; next_inspection_focus: string[] }

export interface Readiness { ready: boolean; completeness_pct: number; checks: { item: string; ok: boolean; required: boolean }[] }

export interface SourceResult<T = Record<string, unknown>> { status: "ok" | "indisponible" | "non_configure" | "absent"; source: string; data?: T | null; error?: string | null }
export interface Environment {
  soil?: SourceResult; climate?: SourceResult<{ annual_rainfall_mm?: { mean: number; min: number; max: number }; rainy_seasons?: string[]; bimodal?: boolean;
    hot_days_per_year?: number; longest_dry_spell_in_rainy_season_days?: number; years?: string }>;
  relief?: SourceResult<{ altitude_m?: { min: number; max: number }; max_slope_pct?: number; slope_class?: string; landscape_position?: string }>;
  access?: SourceResult<{ route?: { distance_km: number; name?: string } | null; cours_eau?: { distance_km: number; name?: string } | null; marche?: { distance_km: number; name?: string } | null }>;
  zone?: { confirmed: boolean; basis: string; candidates: { zone: number; name: string; description?: string | null }[] };
  soil_reading?: { parameter: string; value: number; level: string; comment: string; uncertainty?: string | null }[];
  fetched_at?: string;
}

export const CALL_STATUS: Record<string, [string, "green" | "amber" | "red" | "blue" | "neutral" | "purple"]> = {
  brouillon: ["Brouillon", "neutral"], publie: ["Publié", "blue"], attribution_proposee: ["Attribution proposée", "amber"], attribue: ["Attribué", "purple"],
  concede: ["Concédé", "green"], infructueux: ["Infructueux", "neutral"], annule: ["Annulé", "red"],
};
export const PHASE: Record<string, string> = { a_venir: "À venir", ouvert: "Candidatures ouvertes", cloture: "Candidatures closes" };
export const CONTRACT: Record<string, string> = { concession: "Concession", bail_ordinaire: "Bail ordinaire", bail_emphyteotique: "Bail emphytéotique" };
export const APP_STATUS: Record<string, [string, "green" | "amber" | "red" | "blue" | "neutral" | "purple"]> = {
  deposee: ["Déposée", "blue"], retiree: ["Retirée", "neutral"], retenue: ["Retenue", "green"], non_retenue: ["Non retenue", "neutral"], desistement: ["Désistement", "neutral"],
};
