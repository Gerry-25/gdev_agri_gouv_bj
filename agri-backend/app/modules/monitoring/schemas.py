from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    SAIN = "Sain"
    ATTAQUE_PARASITAIRE = "Attaque parasitaire"
    MALADIE = "Maladie"


class Severity(str, Enum):
    AUCUNE = "Aucune"
    FAIBLE = "Faible"
    MOYENNE = "Moyenne"
    CRITIQUE = "Critique"


class DiagnosisResult(BaseModel):
    """Schéma imposé à Gemini pour sa réponse JSON."""

    crop_identified: str = Field(..., description="Nom de la culture identifiée")
    health_status: HealthStatus = Field(..., description="État sanitaire de la plante")
    disease_name: Optional[str] = Field(None, description="Nom de la maladie ou du ravageur, null si la plante est saine")
    severity: Severity = Field(..., description="Gravité ; 'Aucune' si la plante est saine")
    symptoms: List[str] = Field(default_factory=list, description="Liste des symptômes observés")
    treatment_advice: str = Field(..., description="Conseils de traitement adaptés au contexte local")
    confidence_score: float = Field(..., ge=0, le=1, description="Indice de certitude entre 0 et 1")


class DiagnosisResponse(DiagnosisResult):
    is_simulation: bool = False
    alert_id: Optional[str] = None
