from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.core.benin import CommuneField, DepartmentField, PhoneField

OfferStatus = Literal["active", "sold", "withdrawn"]


class HarvestOfferCreate(BaseModel):
    product_name: str = Field(..., min_length=2, max_length=100, examples=["Ananas Pain de Sucre"])
    quantity_kg: float = Field(..., gt=0)
    unit_price_fcfa: float = Field(..., gt=0)
    contact_phone: PhoneField
    land_id: Optional[str] = Field(None, description="Parcelle d'origine : renseigne la localisation et assure la traçabilité")
    location_commune: Optional[CommuneField] = None
    department: Optional[DepartmentField] = None

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
    created_at: datetime
    updated_at: datetime
    tel_url: str = Field(..., description="Lien d'appel direct (tel:)")
    whatsapp_url: str = Field(..., description="Lien WhatsApp avec message pré-rempli")
