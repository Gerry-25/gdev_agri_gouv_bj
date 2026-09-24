from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.errors import DuplicateKeyError

from app.core import geo
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, require_roles
from app.core.utils import parse_object_id, serialize_doc, utcnow
from app.modules.lands import service
from app.modules.lands.schemas import (
    DisputeOut,
    DisputeReport,
    DisputeStatus,
    DisputeUpdate,
    HarvestCreate,
    HarvestOut,
    LandBoundaryInput,
    LandCreateSchema,
    LandOut,
    LandRegistrationResult,
    LandUpdateSchema,
)

router = APIRouter(prefix="/lands", tags=["Gestion Foncière"])

_CADASTRAL_CONFLICT = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette référence cadastrale est déjà enregistrée.")


def land_feature(doc: dict) -> dict:
    return geo.feature(doc["boundary"], {
        "id": str(doc["_id"]),
        "npi_owner": doc["npi_owner"],
        "department": doc["department"],
        "commune": doc["commune"],
        "locality": doc.get("locality"),
        "crop_type": doc["crop_type"],
        "surface_hectares": doc["surface_hectares"],
        "estimated_yield_kg": doc["estimated_yield_kg"],
        "dispute_flag": doc["dispute_flag"],
    })


# --- Parcelles de l'utilisateur -------------------------------------------------

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=LandRegistrationResult)
async def register_land(
    payload: LandCreateSchema,
    db=Depends(get_database),
    user: CurrentUser = Depends(require_roles("farmer")),
):
    poly, info, warnings = service.geometry_from_boundary(payload.boundary)
    overlaps = service.reject_own_overlaps(await service.find_overlaps(db, poly), user)

    now = utcnow()
    doc = {
        **payload.model_dump(mode="json", exclude={"boundary"}),
        **info,
        "npi_owner": user.npi,  # le propriétaire est l'utilisateur authentifié
        "dispute_flag": False,
        "boundary_history": [],
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db["lands"].insert_one(doc)
    except DuplicateKeyError:
        raise _CADASTRAL_CONFLICT
    doc["_id"] = result.inserted_id

    disputes = await service.open_overlap_disputes(db, doc, overlaps) if overlaps else []
    if disputes:
        warnings.append("Votre parcelle chevauche celle d'un autre exploitant : un litige a été ouvert et sera examiné par un agent.")
    return LandRegistrationResult(
        id=str(result.inserted_id),
        status="registered_with_dispute" if disputes else "registered",
        surface_hectares=info["surface_hectares"],
        overlaps=disputes,
        warnings=warnings,
    )


@router.get("/me", response_model=list[LandOut])
async def get_my_lands(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    cursor = db["lands"].find({"npi_owner": user.npi}).sort("created_at", -1)
    return [serialize_doc(d) async for d in cursor]


@router.get("/me/geojson", summary="Mes parcelles en GeoJSON (pour affichage carte)")
async def get_my_lands_geojson(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    cursor = db["lands"].find({"npi_owner": user.npi})
    return geo.feature_collection([land_feature(d) async for d in cursor])


@router.get("/owner/{npi}", response_model=list[LandOut])
async def get_lands_by_owner(npi: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    # Un exploitant ne voit que ses parcelles ; un agent de l'État voit tout
    if user.npi != npi and not user.is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")
    cursor = db["lands"].find({"npi_owner": npi}).sort("created_at", -1)
    return [serialize_doc(d) async for d in cursor]


# --- Litiges (agents de l'État) -- déclarées avant /{land_id} ---------------------

@router.get("/disputes", response_model=list[DisputeOut])
async def list_disputes(
    db=Depends(get_database),
    _: CurrentUser = Depends(require_roles("state_agent")),
    dispute_status: Optional[DisputeStatus] = Query(None, alias="status"),
    department: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    filters: dict = {}
    if dispute_status:
        filters["status"] = dispute_status
    if department:
        filters["department"] = department
    cursor = db["disputes"].find(filters).sort("created_at", -1).skip(skip).limit(limit)
    return [serialize_doc(d) async for d in cursor]


@router.patch("/disputes/{dispute_id}", response_model=DisputeOut)
async def update_dispute(
    dispute_id: str,
    payload: DisputeUpdate,
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent")),
):
    oid = parse_object_id(dispute_id, "Litige")
    dispute = await db["disputes"].find_one({"_id": oid})
    if not dispute:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Litige introuvable.")
    if dispute["status"] in ("resolu", "rejete"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce litige est déjà clôturé.")

    now = utcnow()
    await db["disputes"].update_one({"_id": oid}, {
        "$set": {"status": payload.status, "resolution_note": payload.resolution_note, "handled_by": agent.npi, "updated_at": now},
        "$push": {"history": {"status": payload.status, "by": agent.npi, "note": payload.resolution_note, "at": now}},
    })
    await service.refresh_dispute_flags(db, dispute["land_ids"])
    return serialize_doc(await db["disputes"].find_one({"_id": oid}))


# --- Parcelle individuelle ------------------------------------------------------

@router.get("/{land_id}", response_model=LandOut)
async def get_land(land_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await service.get_land_or_404(db, land_id)
    service.ensure_owner_or_agent(land, user)
    return serialize_doc(land)


@router.patch("/{land_id}", response_model=LandOut)
async def update_land(
    land_id: str,
    payload: LandUpdateSchema,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    land = await service.get_land_or_404(db, land_id)
    service.ensure_owner(land, user)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aucune modification fournie.")
    try:
        await db["lands"].update_one({"_id": land["_id"]}, {"$set": {**changes, "updated_at": utcnow()}})
    except DuplicateKeyError:
        raise _CADASTRAL_CONFLICT
    return serialize_doc(await db["lands"].find_one({"_id": land["_id"]}))


@router.put("/{land_id}/boundary", response_model=LandRegistrationResult, summary="Remplacer le contour GPS (l'ancien est archivé)")
async def update_land_boundary(
    land_id: str,
    boundary: LandBoundaryInput,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    land = await service.get_land_or_404(db, land_id)
    service.ensure_owner(land, user)
    poly, info, warnings = service.geometry_from_boundary(boundary)
    overlaps = service.reject_own_overlaps(await service.find_overlaps(db, poly, exclude_id=land["_id"]), user)

    now = utcnow()
    await db["lands"].update_one({"_id": land["_id"]}, {
        "$set": {**info, "updated_at": now},
        # Traçabilité : les anciens contours sont conservés
        "$push": {"boundary_history": {"boundary": land["boundary"], "surface_hectares": land["surface_hectares"], "replaced_at": now}},
    })
    land.update(info)
    disputes = await service.open_overlap_disputes(db, land, overlaps) if overlaps else []
    return LandRegistrationResult(
        id=land_id,
        status="updated_with_dispute" if disputes else "updated",
        surface_hectares=info["surface_hectares"],
        overlaps=disputes,
        warnings=warnings,
    )


@router.delete("/{land_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_land(land_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await service.get_land_or_404(db, land_id)
    service.ensure_owner(land, user)
    if land["dispute_flag"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Parcelle en litige : suppression impossible tant que le litige n'est pas clôturé.")
    await db["lands"].delete_one({"_id": land["_id"]})
    await db["harvests"].delete_many({"land_id": land_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{land_id}/geojson")
async def get_land_geojson(land_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await service.get_land_or_404(db, land_id)
    service.ensure_owner_or_agent(land, user)
    return land_feature(land)


# --- Signalement de litige ------------------------------------------------------

@router.post("/{land_id}/disputes", status_code=status.HTTP_201_CREATED, response_model=DisputeOut)
async def report_dispute(
    land_id: str,
    payload: DisputeReport,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    land = await service.get_land_or_404(db, land_id)
    if land["npi_owner"] == user.npi:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vous ne pouvez pas signaler un litige sur votre propre parcelle.")
    now = utcnow()
    doc = {
        **payload.model_dump(),
        "status": "ouvert",
        "land_ids": [land_id],
        "parties_npi": [land["npi_owner"], user.npi],
        "reported_by": user.npi,
        "department": land["department"],
        "commune": land["commune"],
        "history": [{"status": "ouvert", "by": user.npi, "at": now}],
        "created_at": now,
        "updated_at": now,
    }
    res = await db["disputes"].insert_one(doc)
    await service.refresh_dispute_flags(db, [land_id])
    doc["_id"] = res.inserted_id
    return serialize_doc(doc)


@router.get("/{land_id}/disputes", response_model=list[DisputeOut])
async def get_land_disputes(land_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await service.get_land_or_404(db, land_id)
    service.ensure_owner_or_agent(land, user)
    cursor = db["disputes"].find({"land_ids": land_id}).sort("created_at", -1)
    return [serialize_doc(d) async for d in cursor]


# --- Récoltes réelles -----------------------------------------------------------

def _harvest_out(doc: dict, land: dict) -> dict:
    out = serialize_doc(doc)
    surface = land.get("surface_hectares") or 0
    out["yield_kg_per_ha"] = round(doc["actual_yield_kg"] / surface, 1) if surface else None
    return out


@router.post("/{land_id}/harvests", status_code=status.HTTP_201_CREATED, response_model=HarvestOut)
async def record_harvest(
    land_id: str,
    payload: HarvestCreate,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    land = await service.get_land_or_404(db, land_id)
    service.ensure_owner(land, user)
    doc = {
        **payload.model_dump(mode="json"),
        "crop_type": payload.crop_type or land["crop_type"],
        "land_id": land_id,
        "npi_owner": land["npi_owner"],
        "department": land["department"],
        "commune": land["commune"],
        "estimated_yield_kg": land["estimated_yield_kg"],
        "created_at": utcnow(),
    }
    try:
        res = await db["harvests"].insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Une récolte est déjà enregistrée pour cette saison et cette culture.")
    doc["_id"] = res.inserted_id
    return _harvest_out(doc, land)


@router.get("/{land_id}/harvests", response_model=list[HarvestOut])
async def list_harvests(land_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await service.get_land_or_404(db, land_id)
    service.ensure_owner_or_agent(land, user)
    cursor = db["harvests"].find({"land_id": land_id}).sort("season", -1)
    return [_harvest_out(d, land) async for d in cursor]
