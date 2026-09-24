from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.core.benin import CommuneField, DepartmentField, PhoneField
from app.core.utils import CLIENT_REF_DESCRIPTION, CLIENT_REF_PATTERN

DisputeStatus = Literal["ouvert", "en_mediation", "resolu", "rejete"]
OPEN_DISPUTE_STATUSES = ["ouvert", "en_mediation"]
VerificationStatus = Literal["declaree", "verifiee", "rejetee"]
TransferStatus = Literal["en_attente", "approuve", "rejete", "annule"]


class GPSPoint(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, examples=[6.5921])
    longitude: float = Field(..., ge=-180, le=180, examples=[2.5634])
    accuracy_m: Optional[float] = Field(None, ge=0, description="Précision rapportée par le GPS du téléphone (mètres)")


class LandBoundaryInput(BaseModel):
    """Contour de la parcelle : points relevés dans l'ordre en faisant le tour du terrain."""

    points: list[GPSPoint] = Field(..., min_length=3, max_length=1000)
    capture_method: Literal["gps_walk", "map_drawing", "survey"] = Field(
        default="gps_walk",
        description="gps_walk : tour du champ avec le téléphone ; map_drawing : tracé sur carte ; survey : relevé de géomètre",
    )


class LandCreateSchema(BaseModel):
    department: DepartmentField = Field(..., examples=["Ouémé"])
    commune: CommuneField = Field(..., examples=["Dangbo"])
    locality: Optional[str] = Field(None, max_length=100, description="Village ou arrondissement")
    crop_type: str = Field(..., min_length=2, max_length=60, examples=["Manioc"])
    estimated_yield_kg: float = Field(..., ge=0)
    cadastral_reference: Optional[str] = Field(default=None, max_length=50, examples=["REF-BEN-0001"])
    boundary: LandBoundaryInput
    client_ref: Optional[str] = Field(None, pattern=CLIENT_REF_PATTERN, description=CLIENT_REF_DESCRIPTION)


class LandUpdateSchema(BaseModel):
    locality: Optional[str] = Field(None, max_length=100)
    crop_type: Optional[str] = Field(None, min_length=2, max_length=60)
    estimated_yield_kg: Optional[float] = Field(None, ge=0)
    cadastral_reference: Optional[str] = Field(None, max_length=50)


class LandOut(BaseModel):
    id: str
    npi_owner: str
    department: str
    commune: str
    locality: Optional[str] = None
    crop_type: str
    estimated_yield_kg: float
    cadastral_reference: Optional[str] = None
    surface_hectares: float = Field(..., description="Calculée à partir du contour GPS")
    perimeter_m: float
    boundary: dict = Field(..., description="Polygone GeoJSON [longitude, latitude]")
    centroid: dict = Field(..., description="Point GeoJSON au centre de la parcelle")
    points_count: int
    gps_accuracy_mean_m: Optional[float] = None
    capture_method: str
    dispute_flag: bool
    verification_status: VerificationStatus = "declaree"
    verification_note: Optional[str] = None
    verified_at: Optional[datetime] = None
    ownership_history: list[dict] = []
    client_ref: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class OverlapInfo(BaseModel):
    land_id: Optional[str] = None
    domain_id: Optional[str] = Field(None, description="Renseigné si le chevauchement concerne une terre de l'État")
    overlap_m2: float
    dispute_id: str


class LandRegistrationResult(BaseModel):
    id: str
    status: Literal["registered", "registered_with_dispute", "updated", "updated_with_dispute", "already_registered"]
    surface_hectares: float
    overlaps: list[OverlapInfo] = []
    warnings: list[str] = []


class DisputeReport(BaseModel):
    type: Literal["revendication", "limite", "autre"] = Field(
        ..., description="revendication : je suis le propriétaire ; limite : désaccord sur la bordure"
    )
    reason: str = Field(..., min_length=10, max_length=2000)
    contact_phone: Optional[PhoneField] = None


class DisputeUpdate(BaseModel):
    status: Literal["en_mediation", "resolu", "rejete"]
    resolution_note: str = Field(..., min_length=5, max_length=2000)


class DisputeOut(BaseModel):
    id: str
    type: str
    status: DisputeStatus
    land_ids: list[str]
    domain_id: Optional[str] = None
    parties_npi: list[str]
    reported_by: str
    reason: str
    department: Optional[str] = None
    commune: Optional[str] = None
    overlap_area_m2: Optional[float] = None
    contact_phone: Optional[str] = None
    resolution_note: Optional[str] = None
    history: list[dict] = []
    created_at: datetime
    updated_at: datetime


class HarvestCreate(BaseModel):
    season: str = Field(..., pattern=r"^\d{4}(-[A-Z0-9]{1,3})?$", examples=["2026-A"], description="Année, avec suffixe de saison facultatif")
    crop_type: Optional[str] = Field(None, min_length=2, max_length=60, description="Par défaut : la culture de la parcelle")
    actual_yield_kg: float = Field(..., ge=0)
    harvest_date: Optional[date] = None


class HarvestOut(BaseModel):
    id: str
    land_id: str
    season: str
    crop_type: str
    actual_yield_kg: float
    estimated_yield_kg: Optional[float] = None
    yield_kg_per_ha: Optional[float] = None
    harvest_date: Optional[date] = None
    created_at: datetime


class LandVerification(BaseModel):
    status: Literal["verifiee", "rejetee"]
    note: str = Field(..., min_length=3, max_length=1000, description="Ex. : visite terrain du 12/09, bornes conformes")


class TransferRequest(BaseModel):
    new_owner_npi: str = Field(..., pattern=r"^\d{10}$")
    reason: Literal["vente", "heritage", "donation", "autre"]
    note: Optional[str] = Field(None, max_length=1000)


class TransferDecision(BaseModel):
    status: Literal["approuve", "rejete", "annule"] = Field(..., description="approuve/rejete : agent ; annule : demandeur")
    note: Optional[str] = Field(None, max_length=1000)


class TransferOut(BaseModel):
    id: str
    land_id: str
    from_npi: str
    new_owner_npi: str
    reason: str
    note: Optional[str] = None
    status: TransferStatus
    department: str
    commune: str
    decision_note: Optional[str] = None
    decided_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
