from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LandCreateSchema(BaseModel):
    department: str = Field(..., min_length=2, max_length=60, examples=["Ouémé"])
    commune: str = Field(..., min_length=2, max_length=60, examples=["Dangbo"])
    crop_type: str = Field(..., min_length=2, max_length=60, examples=["Manioc"])
    surface_hectares: float = Field(..., gt=0, le=100_000)
    estimated_yield_kg: float = Field(..., ge=0)
    cadastral_reference: Optional[str] = Field(default=None, max_length=50, examples=["REF-BEN-0001"])


class LandOut(LandCreateSchema):
    id: str
    npi_owner: str
    dispute_flag: bool
    created_at: datetime
