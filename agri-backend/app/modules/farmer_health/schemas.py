from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


UrgencyLevel = Literal["vitale", "urgente", "moderee", "faible"]
HealthCategory = Literal[
    "intoxication_pesticide",
    "traumatisme_agricole",
    "morsure_piqure",
    "coup_chaleur_deshydratation",
    "infectieux_paludisme",
    "autre",
]
AlertStatus = Literal["signale", "pris_en_charge", "en_cours", "resolu"]
PatientRelation = Literal["exploitant", "famille", "ouvrier_agricole"]
ServiceType = Literal["centre_de_sante", "hopital_de_zone", "agent_communautaire", "samu_urgences", "clinique_mobile"]
InterventionType = Literal["consultation", "evacuation_urgence", "soins_premiers_secours", "suivi_a_domicile"]


class HealthRecommendation(BaseModel):
    """Sortie structurée de l'IA pour l'analyse des symptômes et premiers secours."""
    urgency_level: UrgencyLevel = Field(..., description="Niveau d'urgence médicale évalué")
    urgency_label: str = Field(..., description="Intitulé clair de l'urgence (ex: Urgence vitale)")
    category: HealthCategory = Field(..., description="Catégorie de pathologie ou incident")
    category_label: str = Field(..., description="Libellé lisible de la catégorie")
    first_aid_steps: list[str] = Field(..., description="Gestes de premiers secours immédiats à réaliser")
    things_to_avoid: list[str] = Field(..., description="Contre-indications absolues et gestes dangereux à proscrire")
    medical_orientation: str = Field(..., description="Orientation médicale recommandée")
    simple_summary: str = Field(..., description="Résumé rassurant et explicatif en 2-3 phrases")


class HealthAlertCreate(BaseModel):
    """Données soumises par l'exploitant pour signaler un problème de santé."""
    patient_name: Optional[str] = Field(None, description="Nom du patient (défaut: nom de l'exploitant)")
    patient_relation: str = Field("exploitant", description="Lien avec l'exploitant (ex: exploitant, famille, ouvrier)")
    phone: str = Field(..., description="Numéro de téléphone d'urgence joignable")
    department: str = Field(..., description="Département de l'incident")
    commune: str = Field(..., description="Commune de l'incident")
    locality: Optional[str] = Field(None, description="Village, quartier ou lieu-dit")
    land_id: Optional[str] = Field(None, description="Identifiant de la parcelle concernée (optionnel)")
    symptoms: str = Field(..., min_length=5, description="Description détaillée des symptômes ressentis")
    suspected_cause: Optional[str] = Field(None, description="Cause suspectée (ex: produit chimique, morsure, chaleur)")
    work_related: bool = Field(True, description="Incident survenu lors des travaux agricoles")
    urgency_perceived: UrgencyLevel = Field("moderee", description="Niveau d'urgence ressenti par le déclarant")


class ServiceAssignment(BaseModel):
    """Affectation d'un service de santé par un agent ou superviseur."""
    facility_name: str = Field(..., description="Nom de la structure de santé (ex: CSA Dangbo)")
    contact_phone: Optional[str] = Field(None, description="Téléphone de la structure ou du soignant")
    service_type: str = Field("centre_de_sante", description="Type de structure de santé")
    intervention_type: str = Field("consultation", description="Type d'intervention planifiée")
    instructions: Optional[str] = Field(None, description="Consignes pour l'exploitant ou l'équipe soignante")


class HealthStatusUpdate(BaseModel):
    """Mise à jour du statut de prise en charge par un agent."""
    status: AlertStatus = Field(..., description="Nouveau statut de l'alerte")
    notes: Optional[str] = Field(None, description="Notes ou compte-rendu de suivi")


class HealthFacilityItem(BaseModel):
    """Structure médicale référencée."""
    name: str
    department: str
    commune: str
    phone: Optional[str] = None
    type: ServiceType


class HealthAlertOut(BaseModel):
    """Alerte de santé avec analyse IA et prise en charge."""
    id: str
    npi: str
    patient_name: str
    patient_relation: PatientRelation
    phone: str
    department: str
    commune: str
    locality: Optional[str] = None
    land_id: Optional[str] = None
    symptoms: str
    suspected_cause: Optional[str] = None
    work_related: bool
    urgency_perceived: UrgencyLevel
    urgency_level: UrgencyLevel
    urgency_label: str
    category: HealthCategory
    category_label: str
    ai_recommendation: dict[str, Any]
    status: AlertStatus
    assigned_service: Optional[dict[str, Any]] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class HealthStatsOut(BaseModel):
    """Statistiques sanitaires globales pour le tableau de bord agent."""
    total_alerts: int
    pending_alerts: int
    in_treatment_alerts: int
    resolved_alerts: int
    vital_urgencies: int
    by_urgency: dict[str, int]
    by_category: dict[str, int]
    by_department: dict[str, int]
    recent_hotspots: list[dict[str, Any]]
