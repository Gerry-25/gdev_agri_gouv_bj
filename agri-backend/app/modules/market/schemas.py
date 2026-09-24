from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.auth.schemas import PHONE_PATTERN


class HarvestOfferCreate(BaseModel):
    product_name: str = Field(..., min_length=2, max_length=100, examples=["Ananas Pain de Sucre"])
    quantity_kg: float = Field(..., gt=0)
    unit_price_fcfa: float = Field(..., gt=0)
    location_commune: str = Field(..., min_length=2, max_length=60)
    contact_phone: str = Field(..., pattern=PHONE_PATTERN)


class HarvestOfferOut(HarvestOfferCreate):
    id: str
    farmer_npi: str
    status: str
    created_at: datetime
