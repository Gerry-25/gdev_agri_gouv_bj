"""Domaine privé agricole de l'État : terres, appels à candidatures et concessions.

Vocabulaire aligné sur le Code foncier et domanial : la concession sur le domaine privé est l'acte par
lequel l'autorité attribue une parcelle à une personne privée, à charge de la mettre en valeur selon un
cahier des charges, pour une durée déterminée et contre une redevance annuelle. L'application prépare et
trace la procédure ; l'acte officiel reste délivré par l'autorité compétente et sa référence est enregistrée.
"""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.core.benin import CommuneField, DepartmentField
from app.modules.lands.schemas import LandBoundaryInput, OverlapInfo

DomainStatus = Literal["disponible", "appel_en_cours", "attribue", "retire"]
ContractType = Literal["concession", "bail_ordinaire", "bail_emphyteotique"]
CallStatus = Literal["brouillon", "publie", "attribution_proposee", "attribue", "concede", "infructueux", "annule"]
CallPhase = Literal["a_venir", "ouvert", "cloture"]
ApplicationStatus = Literal["deposee", "retiree", "retenue", "non_retenue", "desistement"]
ConcessionStatus = Literal["en_attente_acte", "active", "retiree", "terminee", "annulee"]


# --- Terres du domaine privé de l'État ------------------------------------------

class DomainCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=120, examples=["Ferme domaniale de Dangbo - lot 2"])
    department: DepartmentField
    commune: CommuneField
    locality: Optional[str] = Field(None, max_length=100)
    land_title_ref: Optional[str] = Field(None, max_length=100, description="Référence du titre foncier ou de l'immatriculation ANDF")
    suitable_crops: list[str] = Field(default_factory=list, max_length=20)
    description: Optional[str] = Field(None, max_length=3000)
    boundary: LandBoundaryInput


class DomainUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=120)
    locality: Optional[str] = Field(None, max_length=100)
    land_title_ref: Optional[str] = Field(None, max_length=100)
    suitable_crops: Optional[list[str]] = Field(None, max_length=20)
    description: Optional[str] = Field(None, max_length=3000)


class DomainOut(BaseModel):
    id: str
    name: str
    department: str
    commune: str
    locality: Optional[str] = None
    land_title_ref: Optional[str] = None
    suitable_crops: list[str] = []
    description: Optional[str] = None
    surface_hectares: float
    perimeter_m: float
    boundary: dict
    centroid: dict
    status: DomainStatus
    dispute_flag: bool
    current_call_id: Optional[str] = None
    current_concession_id: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime


class DomainRegistrationResult(BaseModel):
    id: str
    surface_hectares: float
    status: Literal["registered", "registered_with_dispute"]
    overlaps: list[OverlapInfo] = []
    warnings: list[str] = []


class ReasonInput(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000)


# --- Appels à candidatures ------------------------------------------------------

class CallBase(BaseModel):
    title: str = Field(..., min_length=5, max_length=150)
    description: str = Field(..., min_length=10, max_length=5000)
    cahier_des_charges: str = Field(..., min_length=20, max_length=20_000, description="Obligations de mise en valeur (Markdown)")
    allowed_crops: list[str] = Field(..., min_length=1, max_length=20)
    contract_type: ContractType = "concession"
    duration_years: int = Field(..., ge=1, le=50)
    annual_fee_fcfa_per_ha: float = Field(..., ge=0, description="Redevance annuelle")
    mise_en_valeur_months: int = Field(..., ge=1, le=60, description="Délai de mise en valeur après l'acte")
    min_score: float = Field(50, ge=0, le=100, description="Score de performance minimal pour candidater")
    eligible_departments: list[DepartmentField] = Field(default_factory=list, description="Vide = tout le Bénin")
    opens_at: datetime
    closes_at: datetime


class CallCreate(CallBase):
    @model_validator(mode="after")
    def _dates(self):
        if self.closes_at <= self.opens_at:
            raise ValueError("La date de clôture doit suivre la date d'ouverture.")
        return self


class AwardInfo(BaseModel):
    application_id: str
    farmer_npi: str
    farmer_name: Optional[str] = None
    score: float
    proposed_by: str
    proposed_at: datetime
    justification: str
    deviation_from_ranking: bool = Field(..., description="Vrai si un candidat mieux classé a été écarté")
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    contest_until: Optional[datetime] = None
    acceptance_deadline: Optional[datetime] = None
    accepted_at: Optional[datetime] = None


class CallOut(CallBase):
    id: str
    domain_id: str
    domain_name: str
    department: str
    commune: str
    surface_hectares: float
    status: CallStatus
    phase: Optional[CallPhase] = None
    applications_count: int = 0
    created_by: str
    published_by: Optional[str] = None
    published_at: Optional[datetime] = None
    award: Optional[AwardInfo] = None
    history: list[dict] = []
    created_at: datetime
    updated_at: datetime


class PublicCallOut(BaseModel):
    """Vue publique d'un appel (transparence de la procédure)."""
    id: str
    title: str
    description: str
    cahier_des_charges: str
    allowed_crops: list[str]
    contract_type: ContractType
    duration_years: int
    annual_fee_fcfa_per_ha: float
    mise_en_valeur_months: int
    min_score: float
    eligible_departments: list[str]
    opens_at: datetime
    closes_at: datetime
    status: CallStatus
    phase: Optional[CallPhase] = None
    domain_name: str
    department: str
    commune: str
    surface_hectares: float
    boundary: dict
    applications_count: int
    awarded_to_name: Optional[str] = None
    contest_until: Optional[datetime] = None


class ApplicationCreate(BaseModel):
    proposed_crop: str = Field(..., min_length=2, max_length=60)
    planned_yield_kg: float = Field(..., ge=0, description="Production prévue sur toute la terre, par saison")
    motivation: str = Field(..., min_length=20, max_length=3000)
    experience_years: Optional[int] = Field(None, ge=0, le=80)


class ApplicationOut(ApplicationCreate):
    id: str
    call_id: str
    farmer_npi: str
    farmer_name: Optional[str] = None
    score_at_submission: float
    score_components: list[dict] = []
    status: ApplicationStatus
    rank: Optional[int] = None
    current_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class EligibilityOut(BaseModel):
    eligible: bool
    reasons: list[str]
    score: float
    min_score: float
    already_applied: bool


class AwardProposal(BaseModel):
    application_id: str
    justification: str = Field(..., min_length=20, max_length=3000)


class AwardDecision(BaseModel):
    approve: bool
    note: str = Field(..., min_length=5, max_length=2000)


class AcceptanceInput(BaseModel):
    accept: bool
    note: Optional[str] = Field(None, max_length=1000)


class ContestationCreate(BaseModel):
    reason: str = Field(..., min_length=20, max_length=3000)


class ContestationDecision(BaseModel):
    decision: Literal["fondee", "rejetee"]
    note: str = Field(..., min_length=5, max_length=2000)


class ContestationOut(BaseModel):
    id: str
    call_id: str
    npi: str
    reason: str
    status: Literal["ouverte", "fondee", "rejetee"]
    decision_note: Optional[str] = None
    decided_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# --- Concessions ----------------------------------------------------------------

class OfficialActInput(BaseModel):
    act_ref: str = Field(..., min_length=3, max_length=100, description="Numéro de l'arrêté, de la convention ou du bail")
    act_date: date
    authority: str = Field(..., min_length=3, max_length=150, examples=["Préfecture de l'Ouémé"])


class ConcessionReportCreate(BaseModel):
    season: str = Field(..., pattern=r"^\d{4}(-[A-Z0-9]{1,3})?$", examples=["2026-A"])
    crop_type: str = Field(..., min_length=2, max_length=60)
    area_cultivated_ha: float = Field(..., gt=0)
    actual_yield_kg: float = Field(..., ge=0)


class InspectionCreate(BaseModel):
    mise_en_valeur_pct: float = Field(..., ge=0, le=100, description="Part de la terre effectivement mise en valeur")
    compliant: bool = Field(..., description="Respect du cahier des charges")
    note: str = Field(..., min_length=5, max_length=2000)
    inspection_date: Optional[date] = None


class PaymentCreate(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    amount_fcfa: float = Field(..., gt=0)
    receipt_ref: str = Field(..., min_length=3, max_length=100)


class TerminationInput(BaseModel):
    status: Literal["retiree", "terminee"]
    reason: Literal["defaut_mise_en_valeur", "non_paiement", "manquement_cahier_des_charges", "fin_de_contrat", "renonciation", "autre"]
    note: str = Field(..., min_length=5, max_length=2000)
