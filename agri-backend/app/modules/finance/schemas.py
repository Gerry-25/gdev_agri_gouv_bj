from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


FinancialProductType = Literal["credit", "assurance", "financement"]
ApplicationStatus = Literal["soumis", "analyse_ia", "approuve", "rejete", "debourse_actif", "clos"]
AiVerdict = Literal["favorable", "favorable_sous_conditions", "defavorable"]


class FinancialAiEvaluation(BaseModel):
    """Analyse multidimensionnelle d'éligibilité et de solvabilité générée par l'IA."""
    score: float = Field(..., ge=0, le=100, description="Score d'éligibilité / solvabilité / viabilité (0 à 100)")
    verdict: str = Field(..., description="Verdict de l'évaluation : favorable, favorable_sous_conditions, defavorable")
    verdict_label: str = Field(..., description="Libellé lisible du verdict")
    strengths: list[str] = Field(default_factory=list, description="Points forts du dossier et du profil exploitant")
    risks: list[str] = Field(default_factory=list, description="Facteurs de risque ou points de vigilance identifiés")
    recommended_conditions: list[str] = Field(default_factory=list, description="Conditions ou garanties recommandées pour l'octroi")
    recommended_amount: Optional[float] = Field(None, description="Montant recommandé après analyse de capacité")
    summary: str = Field(..., description="Synthèse explicative de la recommandation pour l'agent")
    farmer_advice: str = Field(..., description="Conseils personnalisés rédigés pour l'exploitant")
    type_specific_metrics: dict[str, Any] = Field(default_factory=dict, description="Métriques spécifiques (ratio d'endettement, indice climatique, effet levier)")


class OfferBase(BaseModel):
    """Caractéristiques d'une offre financière agricole."""
    title: str = Field(..., description="Intitulé de l'offre (ex: Microcrédit Campagne Coton FNDA)")
    type: FinancialProductType = Field(..., description="Type de produit : credit, assurance ou financement")
    category_label: str = Field(..., description="Libellé de catégorie lisible")
    institution: str = Field(..., description="Organisme ou bailleur (FNDA, CLCAM, MAEP, AMAB...)")
    description: str = Field(..., description="Présentation détaillée de l'offre et ses objectifs")
    amount_min: float = Field(..., ge=0, description="Montant minimum en FCFA")
    amount_max: float = Field(..., ge=0, description="Montant maximum en FCFA")
    currency: str = Field("FCFA", description="Devise (FCFA par défaut)")
    interest_rate_pct: Optional[float] = Field(None, description="Taux d'intérêt annuel ou de campagne en % (pour les crédits)")
    duration_months: Optional[int] = Field(None, description="Durée de remboursement en mois (pour les crédits)")
    grace_period_months: Optional[int] = Field(None, description="Période de différé en mois")
    premium_rate_pct: Optional[float] = Field(None, description="Taux de prime annuelle en % (pour les assurances)")
    coverage_details: Optional[str] = Field(None, description="Plafond ou conditions de déclenchement indiciel (assurances)")
    subsidy_pct: Optional[float] = Field(None, description="Taux de prise en charge par subvention en % (financements)")
    eligible_departments: list[str] = Field(default_factory=list, description="Départements éligibles (vide = national)")
    eligible_crops: list[str] = Field(default_factory=list, description="Cultures éligibles (vide = toutes cultures)")
    min_performance_score: Optional[float] = Field(None, description="Score de performance agricole recommandé")
    requirements: list[str] = Field(default_factory=list, description="Conditions requises et justificatifs demandés")
    active: bool = Field(True, description="Offre actuellement ouverte aux candidatures")


class OfferCreate(OfferBase):
    pass


class OfferOut(OfferBase):
    id: str
    created_at: datetime
    updated_at: datetime


class ApplicationCreate(BaseModel):
    """Demande formulée par un exploitant agricole."""
    offer_id: str = Field(..., description="Identifiant de l'offre financière postulée")
    land_id: Optional[str] = Field(None, description="Parcelle d'exploitation ciblée (recommandé)")
    crop_type: str = Field(..., description="Culture ou spéculation concernée (ex: Maïs, Coton, Maraîchage)")
    surface_ha: float = Field(..., gt=0, description="Surface cultivée concernée en hectares")
    amount_requested: float = Field(..., gt=0, description="Montant demandé en FCFA")
    project_description: str = Field(..., min_length=10, description="Description du projet et utilisation prévue des fonds")
    declared_harvest_estimate_kg: Optional[float] = Field(None, description="Estimation de la récolte attendue en kg")
    guarantees_or_notes: Optional[str] = Field(None, description="Garanties proposées ou plan de remboursement indicatif")


class ApplicationDecision(BaseModel):
    """Validation, ajustement ou rejet par un agent ou superviseur de l'État."""
    status: Literal["approuve", "rejete", "en_instruction", "analyse_ia"] = Field(..., description="Nouvelle décision prise")
    amount_approved: Optional[float] = Field(None, description="Montant approuvé (peut être révisé selon capacité)")
    interest_rate_approved: Optional[float] = Field(None, description="Taux d'intérêt ou prime validé")
    duration_approved_months: Optional[int] = Field(None, description="Durée de validité ou d'échéance validée")
    conditions: list[str] = Field(default_factory=list, description="Conditions obligatoires fixées par l'agent")
    motivation_or_notes: str = Field(..., min_length=3, description="Justification officielle de la décision")


class ApplicationDisbursement(BaseModel):
    """Notification de déboursement ou activation de couverture."""
    contract_ref: Optional[str] = Field(None, description="Numéro de contrat ou référence officielle")
    payment_reference: Optional[str] = Field(None, description="Référence du virement ou ordre de paiement")
    notes: Optional[str] = Field(None, description="Observations complémentaires")


class ApplicationOut(BaseModel):
    id: str
    offer_id: str
    offer_title: str
    offer_type: str
    offer_institution: str
    farmer_npi: str
    farmer_name: str
    farmer_phone: str
    department: str
    commune: str
    land_id: Optional[str] = None
    land_title: Optional[str] = None
    crop_type: str
    surface_ha: float
    amount_requested: float
    amount_approved: Optional[float] = None
    project_description: str
    declared_harvest_estimate_kg: Optional[float] = None
    guarantees_or_notes: Optional[str] = None
    status: str
    ai_evaluation: Optional[dict[str, Any]] = None
    agent_decision: Optional[dict[str, Any]] = None
    disbursement: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class FinanceStatsOut(BaseModel):
    total_applications: int
    pending_applications: int
    approved_applications: int
    rejected_applications: int
    disbursed_applications: int
    total_amount_requested: float
    total_amount_approved: float
    by_type: dict[str, int]
    by_status: dict[str, int]
    by_department: dict[str, int]
    approval_rate_pct: float
