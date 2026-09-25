from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.core.benin import CommuneField, DepartmentField, PhoneField
from app.core.utils import CLIENT_REF_DESCRIPTION, CLIENT_REF_PATTERN

OfferStatus = Literal["active", "sold", "withdrawn"]


class HarvestOfferCreate(BaseModel):
    product_name: str = Field(..., min_length=2, max_length=100, examples=["Ananas Pain de Sucre"])
    quantity_kg: float = Field(..., gt=0)
    unit_price_fcfa: float = Field(..., gt=0)
    contact_phone: PhoneField
    land_id: Optional[str] = Field(None, description="Parcelle d'origine : renseigne la localisation et assure la traçabilité")
    location_commune: Optional[CommuneField] = None
    department: Optional[DepartmentField] = None
    description: Optional[str] = Field(None, max_length=800, description="Qualité, conditionnement, conditions de livraison")
    client_ref: Optional[str] = Field(None, pattern=CLIENT_REF_PATTERN, description=CLIENT_REF_DESCRIPTION)

    @model_validator(mode="after")
    def _location_required(self):
        if not self.land_id and not self.location_commune:
            raise ValueError("Indiquez la parcelle d'origine (land_id) ou la commune (location_commune).")
        return self


class HarvestOfferUpdate(BaseModel):
    product_name: Optional[str] = Field(None, min_length=2, max_length=100)
    quantity_kg: Optional[float] = Field(None, gt=0)
    unit_price_fcfa: Optional[float] = Field(None, gt=0)
    contact_phone: Optional[PhoneField] = None
    description: Optional[str] = Field(None, max_length=800)


class OfferStatusUpdate(BaseModel):
    status: OfferStatus
    sold_quantity_kg: Optional[float] = Field(None, gt=0, description="Par défaut : toute la quantité")
    sold_unit_price_fcfa: Optional[float] = Field(None, gt=0, description="Par défaut : le prix affiché")


class HarvestOfferOut(BaseModel):
    id: str
    farmer_npi: str
    product_name: str
    quantity_kg: float
    unit_price_fcfa: float
    contact_phone: str
    land_id: Optional[str] = None
    location_commune: str
    department: Optional[str] = None
    status: OfferStatus
    sold_quantity_kg: Optional[float] = None
    sold_unit_price_fcfa: Optional[float] = None
    sold_at: Optional[datetime] = None
    interest_count: int = 0
    description: Optional[str] = None
    origin_verified: bool = Field(False, description="Récolte rattachée à une parcelle vérifiée par un agent")
    client_ref: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    tel_url: str = Field(..., description="Lien d'appel direct (tel:)")
    whatsapp_url: str = Field(..., description="Lien WhatsApp avec message pré-rempli")


class InterestCreate(BaseModel):
    message: Optional[str] = Field(None, max_length=500, examples=["Je peux acheter 500 kg livrés à Cotonou."])
    quantity_kg: Optional[float] = Field(None, gt=0)


class InterestOut(BaseModel):
    id: str
    offer_id: str
    buyer_npi: str
    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None
    message: Optional[str] = None
    quantity_kg: Optional[float] = None
    created_at: datetime


class MyInterestOut(BaseModel):
    id: str
    offer_id: str
    message: Optional[str] = None
    quantity_kg: Optional[float] = None
    created_at: datetime
    offer: Optional[HarvestOfferOut] = Field(None, description="Absente si l'offre a été supprimée")
