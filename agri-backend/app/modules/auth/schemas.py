from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.core.benin import PhoneField

NPI_PATTERN = r"^\d{10}$"


class UserRole(str, Enum):
    FARMER = "farmer"
    BUYER = "buyer"
    STATE_AGENT = "state_agent"


class CitizenAuthSchema(BaseModel):
    npi: str = Field(..., description="Numéro Personnel d'Identification (10 chiffres)", pattern=NPI_PATTERN)
    phone: PhoneField = Field(..., description="Téléphone mobile (01XXXXXXXX ou +22901XXXXXXXX)")
    full_name: str = Field(..., min_length=2, max_length=120)
    # Le rôle "state_agent" ne peut pas être choisi à l'inscription :
    # il est attribué par un administrateur (voir app/scripts/promote_user.py)
    role: Literal["farmer", "buyer"] = Field(default="farmer", description="farmer ou buyer")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Durée de validité en secondes")
    user_npi: str
    role: UserRole


class UserProfile(BaseModel):
    npi: str
    phone: str
    full_name: str
    role: UserRole
