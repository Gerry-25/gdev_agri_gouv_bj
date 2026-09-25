"""Données complémentaires des terres de l'État et plan de mise en valeur généré par l'IA."""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- Relevé de terrain (agent) ---------------------------------------------------

class LabSoilAnalysis(BaseModel):
    lab_name: str = Field(..., min_length=2, max_length=120)
    sample_date: date
    ph: Optional[float] = Field(None, ge=2, le=11)
    organic_carbon_pct: Optional[float] = Field(None, ge=0, le=30)
    nitrogen_total_pct: Optional[float] = Field(None, ge=0, le=5)
    phosphorus_ppm: Optional[float] = Field(None, ge=0, le=1000)
    potassium_ppm: Optional[float] = Field(None, ge=0, le=5000)
    texture: Optional[str] = Field(None, max_length=60, examples=["limono-sableuse"])
    notes: Optional[str] = Field(None, max_length=1000)


class SiteSurvey(BaseModel):
    survey_date: date
    agroecological_zone: Optional[int] = Field(None, ge=1, le=8, description="Zone confirmée par l'agent (1 à 8)")
    land_use_history: Literal["jachere", "culture", "foret_savane", "paturage", "inconnu"]
    fallow_years: Optional[int] = Field(None, ge=0, le=60)
    last_crops: list[str] = Field(default_factory=list, max_length=10)
    burning_practiced: Optional[bool] = None
    water_sources: list[Literal["forage", "puits", "riviere", "bas_fond", "retenue_eau", "aucune"]] = Field(default_factory=list)
    irrigation_possible: Optional[bool] = None
    flooding_observed: Literal["jamais", "occasionnel", "frequent", "inconnu"] = "inconnu"
    vegetation_cover: Literal["sol_nu", "herbacee", "arbustive", "arboree", "dense"]
    trees_to_preserve: Optional[str] = Field(None, max_length=300, examples=["Karité, néré"])
    erosion: Literal["aucune", "legere", "forte"] = "aucune"
    stoniness: Literal["faible", "moyenne", "forte"] = "faible"
    termite_mounds: Optional[bool] = None
    clearing_needed: Literal["aucun", "leger", "important"] = "leger"
    rainy_season_access: Literal["bonne", "difficile", "impossible"]
    infrastructures: list[Literal["cloture", "magasin", "electricite", "logement", "forage_equipe", "piste_interne"]] = Field(default_factory=list)
    labor_availability: Literal["faible", "moyenne", "bonne"]
    customary_uses: Optional[str] = Field(None, max_length=1000, description="Usages coutumiers ou occupants à respecter")
    observations: Optional[str] = Field(None, max_length=3000)
    lab_soil_analysis: Optional[LabSoilAnalysis] = None


class StateOrientation(BaseModel):
    vocation: Literal["vivrier", "rente_export", "semences", "jeunes_entrepreneurs", "mixte"]
    priority_crops: list[str] = Field(default_factory=list, max_length=10)
    excluded_crops: list[str] = Field(default_factory=list, max_length=10)
    investment_level: Literal["faible", "moyen", "eleve"]
    mechanization: Literal["manuelle", "attelee", "motorisee"]
    min_valorization_pct: float = Field(80, ge=10, le=100)
    notes: Optional[str] = Field(None, max_length=2000)


# --- Plan de mise en valeur (sortie structurée de l'IA) ------------------------------

class Range(BaseModel):
    low: float = Field(..., ge=0)
    high: float = Field(..., ge=0)


class CropSuitability(BaseModel):
    crop: str
    suitability: Literal["elevee", "moyenne", "faible", "deconseillee"]
    score: float = Field(..., ge=0, le=10)
    reasons: list[str]
    limiting_factors: list[str] = Field(default_factory=list)


class CropShare(BaseModel):
    crop: str
    share_pct: float = Field(..., ge=0, le=100)


class CropYield(BaseModel):
    crop: str
    yield_kg_ha: Range


class CalendarStep(BaseModel):
    period: str = Field(..., description="Ex. : « mars - avril »")
    activity: str
    details: str = ""


class Scenario(BaseModel):
    name: str
    orientation: Literal["vivrier", "rente", "mixte"]
    crops: list[str]
    rotation: str
    surface_allocation: list[CropShare]
    yields: list[CropYield]
    costs_fcfa_ha: Range
    revenue_fcfa_ha: Range
    investments: list[str]
    labor_needs: str
    calendar: list[CalendarStep]
    advantages: list[str]
    drawbacks: list[str]


class FertilityAction(BaseModel):
    action: str
    timing: str
    rationale: str


class Risk(BaseModel):
    risk: str
    likelihood: Literal["faible", "moyen", "eleve"]
    mitigation: str


class Indicator(BaseModel):
    indicator: str
    target: str
    deadline_months: int = Field(..., ge=1, le=120)
    how_to_check: str


class ValorizationPlan(BaseModel):
    summary: str
    suitability: list[CropSuitability]
    scenarios: list[Scenario] = Field(..., min_length=1, max_length=3)
    recommended_scenario_index: int = Field(..., ge=0)
    recommendation_rationale: str
    fertility_plan: list[FertilityAction]
    risks: list[Risk]
    valorization_indicators: list[Indicator]
    data_gaps: list[str]
    confidence: Literal["faible", "moyenne", "elevee"]


class PlanReview(BaseModel):
    status: Literal["valide", "a_revoir"]
    expert_name: str = Field(..., min_length=3, max_length=120, description="Agronome ou expert ayant relu")
    organization: str = Field(..., min_length=2, max_length=120, examples=["INRAB", "ATDA"])
    note: str = Field(..., min_length=5, max_length=3000)


class PlanOut(BaseModel):
    id: str
    domain_id: str
    version: int
    plan: ValorizationPlan
    status: Literal["proposition", "valide", "a_revoir"]
    model: str
    data_used: dict
    review: Optional[dict] = None
    created_by: Optional[str] = Field(None, description="Agent ayant généré le plan (la relecture doit venir d'un autre agent)")
    created_at: datetime


class ApplicationReview(BaseModel):
    alignment: Literal["fort", "moyen", "faible"]
    strengths: list[str]
    gaps: list[str]
    risks: list[str]
    questions_for_interview: list[str]
    yield_assessment: str
    comment: str
