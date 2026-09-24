from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.core.benin import CommuneField, DepartmentField, PhoneField

NPI_PATTERN = r"^\d{10}$"
LanguageCode = Literal["fr", "fon", "yo", "en"]


class UserRole(str, Enum):
    FARMER = "farmer"
    BUYER = "buyer"
    STATE_AGENT = "state_agent"


class OtpRequest(BaseModel):
    npi: str = Field(..., description="Numéro Personnel d'Identification (10 chiffres)", pattern=NPI_PATTERN)
    phone: PhoneField = Field(..., description="Téléphone mobile (01XXXXXXXX ou +22901XXXXXXXX)")
    # Champs utilisés uniquement lors de la première connexion (inscription)
    full_name: Optional[str] = Field(None, min_length=2, max_length=120)
    # Le rôle "state_agent" ne peut pas être choisi : il est attribué par un administrateur
    role: Literal["farmer", "buyer"] = "farmer"
    preferred_language: LanguageCode = "fr"


class OtpRequestResponse(BaseModel):
    message: str
    is_new_user: bool
    expires_in: int
    resend_in: int
    delivery: str
    simulated_code: Optional[str] = Field(None, description="Présent uniquement en mode simulation, pour affichage à l'écran")


class OtpVerify(BaseModel):
    npi: str = Field(..., pattern=NPI_PATTERN)
    code: str = Field(..., pattern=r"^\d{4,8}$")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20, max_length=200)


class UserProfile(BaseModel):
    npi: str
    phone: str
    full_name: str
    role: UserRole
    preferred_language: LanguageCode = "fr"
    department: Optional[str] = None
    commune: Optional[str] = None
    created_at: Optional[datetime] = None


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=120)
    preferred_language: Optional[LanguageCode] = None
    department: Optional[DepartmentField] = None
    commune: Optional[CommuneField] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Validité du jeton d'accès en secondes")
    refresh_expires_in: int = Field(..., description="Validité du jeton de rafraîchissement en secondes")
    user: UserProfile
