from datetime import datetime
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


# Couleur d'alerte pour les pictogrammes du frontend
SEVERITY_COLORS = {"Aucune": "green", "Faible": "yellow", "Moyenne": "orange", "Critique": "red"}

LANGUAGES = {"fr": "français", "fon": "fon (fɔngbè)", "yo": "yoruba", "en": "anglais"}


class DiagnosisResult(BaseModel):
    """Schéma imposé à Gemini pour sa réponse JSON."""

    crop_identified: str = Field(..., description="Nom de la culture identifiée")
    health_status: HealthStatus = Field(..., description="État sanitaire de la plante")
    disease_name: Optional[str] = Field(None, description="Nom courant de la maladie ou du ravageur, null si la plante est saine")
    severity: Severity = Field(..., description="Gravité ; 'Aucune' si la plante est saine")
    symptoms: List[str] = Field(default_factory=list, description="Symptômes observés, en mots simples")
    simple_summary: str = Field(..., description="1 à 2 phrases très simples, dans la langue demandée, destinées à être lues à voix haute")
    treatment_steps: List[str] = Field(default_factory=list, description="3 à 5 étapes courtes et concrètes, dans l'ordre")
    treatment_advice: str = Field(..., description="Conseil de traitement détaillé, en langage clair")
    confidence_score: float = Field(..., ge=0, le=1, description="Indice de certitude entre 0 et 1")


class DiagnosisResponse(DiagnosisResult):
    alert_id: Optional[str] = None
    alert_color: str = Field(..., description="green, yellow, orange ou red")
    department: str
    commune: str
    land_id: Optional[str] = None
    location: Optional[dict] = Field(None, description="Point GeoJSON du lieu du diagnostic")
    language: str = "fr"
    is_simulation: bool = False
    image_url: Optional[str] = Field(None, description="Chemin de la photo conservée (authentification requise)")
    client_ref: Optional[str] = None
    observed_at: Optional[datetime] = Field(None, description="Date de prise de la photo (peut précéder l'envoi en mode hors ligne)")
    created_at: Optional[datetime] = None
