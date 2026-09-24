from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.errors import DuplicateKeyError

from app.core import geo
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, require_roles
from app.core.utils import parse_object_id, serialize_doc, utcnow
from app.modules.notifications.service import notify
from app.modules.lands import service
from app.modules.lands.schemas import (
    LandVerification,
    TransferDecision,
    TransferOut,
    TransferRequest,
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
        "verification_status": doc.get("verification_status", "declaree"),
    })


# --- Parcelles de l'utilisateur -------------------------------------------------

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=LandRegistrationResult)
async def register_land(
    payload: LandCreateSchema,
    response: Response,
    db=Depends(get_database),
    user: CurrentUser = Depends(require_roles("farmer")),
):
    async def already_registered():
        if not payload.client_ref:
            return None
        existing = await db["lands"].find_one({"npi_owner": user.npi, "client_ref": payload.client_ref})
        if existing:
            response.status_code = status.HTTP_200_OK
            return LandRegistrationResult(id=str(existing["_id"]), status="already_registered", surface_hectares=existing["surface_hectares"])
        return None

    if (dup := await already_registered()) is not None:
        return dup
    poly, info, warnings = service.geometry_from_boundary(payload.boundary)
    overlaps = service.reject_own_overlaps(await service.find_overlaps(db, poly), user)

    now = utcnow()
    doc = {
        **payload.model_dump(mode="json", exclude={"boundary"}),
        **info,
        "npi_owner": user.npi,  # le propriétaire est l'utilisateur authentifié
        "dispute_flag": False,
        "verification_status": "declaree",
        "boundary_history": [],
        "ownership_history": [],
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db["lands"].insert_one(doc)
    except DuplicateKeyError:
        if (dup := await already_registered()) is not None:  # envoi simultané du même client_ref
            return dup
        raise _CADASTRAL_CONFLICT
    doc["_id"] = result.inserted_id

    disputes = await service.open_overlap_disputes(db, doc, overlaps) if overlaps else []
    if disputes:
        warnings.append("Votre parcelle chevauche celle d'un autre exploitant : un litige a été ouvert et sera examiné par un agent.")
    domain_overlaps = await service.find_overlaps(db, poly, collection="state_domains")
    if domain_overlaps:
        disputes += await service.open_domain_disputes(db, doc, domain_overlaps)
        warnings.append("Votre parcelle empiète sur une terre de l'État : un litige a été ouvert et sera examiné par un agent.")
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
    await service.refresh_dispute_flags(db, dispute["land_ids"], [dispute["domain_id"]] if dispute.get("domain_id") else None)
    labels = {"en_mediation": "en médiation", "resolu": "résolu", "rejete": "rejeté"}
    await notify(db, dispute["parties_npi"], "dispute_updated", "Mise à jour d'un litige",
                 f"Le litige à {dispute.get('commune', '')} est {labels[payload.status]} : {payload.resolution_note}",
                 {"dispute_id": dispute_id, "status": payload.status})
    return serialize_doc(await db["disputes"].find_one({"_id": oid}))


# --- Transferts de propriété (déclarés avant /{land_id}) -------------------------

@router.get("/transfers", response_model=list[TransferOut], summary="Demandes de transfert (agents)")
async def list_transfers(
    db=Depends(get_database),
    _: CurrentUser = Depends(require_roles("state_agent")),
    transfer_status: Optional[str] = Query("en_attente", alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    filters = {"status": transfer_status} if transfer_status else {}
    cursor = db["transfers"].find(filters).sort("created_at", -1).skip(skip).limit(limit)
    return [serialize_doc(d) async for d in cursor]


@router.get("/transfers/me", response_model=list[TransferOut], summary="Transferts que j'ai demandés ou reçus")
async def my_transfers(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    cursor = db["transfers"].find({"$or": [{"from_npi": user.npi}, {"new_owner_npi": user.npi}]}).sort("created_at", -1)
    return [serialize_doc(d) async for d in cursor]


@router.patch("/transfers/{transfer_id}", response_model=TransferOut, summary="Approuver/rejeter (agent) ou annuler (demandeur)")
async def decide_transfer(
    transfer_id: str,
    payload: TransferDecision,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    oid = parse_object_id(transfer_id, "Transfert")
    transfer = await db["transfers"].find_one({"_id": oid})
    if not transfer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfert introuvable.")
    if transfer["status"] != "en_attente":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce transfert est déjà traité.")
    if payload.status == "annule":
        if user.npi != transfer["from_npi"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seul le demandeur peut annuler.")
    elif not user.is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seul un agent peut approuver ou rejeter un transfert.")

    now = utcnow()
    if payload.status == "approuve":
        land = await service.get_land_or_404(db, transfer["land_id"])
        if land["npi_owner"] != transfer["from_npi"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Le propriétaire de la parcelle a changé depuis la demande.")
        if land["dispute_flag"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Parcelle en litige : clôturez le litige avant le transfert.")
        await db["lands"].update_one({"_id": land["_id"]}, {
            "$set": {"npi_owner": transfer["new_owner_npi"], "client_ref": None, "updated_at": now},
            "$push": {"ownership_history": {
                "from_npi": transfer["from_npi"], "to_npi": transfer["new_owner_npi"], "reason": transfer["reason"],
                "transfer_id": transfer_id, "approved_by": user.npi, "at": now,
            }},
        })

    await db["transfers"].update_one({"_id": oid}, {"$set": {
        "status": payload.status, "decision_note": payload.note, "decided_by": user.npi, "updated_at": now,
    }})
    labels = {"approuve": "approuvé", "rejete": "rejeté", "annule": "annulé"}
    await notify(db, [transfer["from_npi"], transfer["new_owner_npi"]], "transfer_updated", "Transfert de parcelle",
                 f"Le transfert de la parcelle à {transfer['commune']} a été {labels[payload.status]}.",
                 {"transfer_id": transfer_id, "land_id": transfer["land_id"], "status": payload.status})
    return serialize_doc(await db["transfers"].find_one({"_id": oid}))


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
        # Un nouveau contour doit être revérifié par un agent
        "$set": {**info, "verification_status": "declaree", "verification_note": None, "verified_at": None, "updated_at": now},
        # Traçabilité : les anciens contours sont conservés
        "$push": {"boundary_history": {"boundary": land["boundary"], "surface_hectares": land["surface_hectares"], "replaced_at": now}},
    })
    land.update(info)
    disputes = await service.open_overlap_disputes(db, land, overlaps) if overlaps else []
    domain_overlaps = await service.find_overlaps(db, poly, collection="state_domains")
    if domain_overlaps:
        disputes += await service.open_domain_disputes(db, land, domain_overlaps)
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
    if await db["transfers"].count_documents({"land_id": land_id, "status": "en_attente"}):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un transfert est en attente pour cette parcelle.")
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
    await notify(db, [land["npi_owner"]], "dispute_opened", "Litige signalé sur votre parcelle",
                 f"Un litige a été signalé sur votre parcelle à {land['commune']}. Un agent va examiner la situation.",
                 {"dispute_id": str(res.inserted_id), "land_id": land_id})
    doc["_id"] = res.inserted_id
    return serialize_doc(doc)


# --- Vérification et transfert d'une parcelle -----------------------------------

@router.patch("/{land_id}/verification", response_model=LandOut, summary="Valider ou rejeter une parcelle après contrôle (agent)")
async def verify_land(
    land_id: str,
    payload: LandVerification,
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent")),
):
    land = await service.get_land_or_404(db, land_id)
    now = utcnow()
    await db["lands"].update_one({"_id": land["_id"]}, {"$set": {
        "verification_status": payload.status, "verification_note": payload.note,
        "verified_by": agent.npi, "verified_at": now, "updated_at": now,
    }})
    msg = "a été vérifiée par un agent" if payload.status == "verifiee" else "n'a pas été validée"
    await notify(db, [land["npi_owner"]], "land_verified", "Vérification de parcelle",
                 f"Votre parcelle à {land['commune']} {msg} : {payload.note}", {"land_id": land_id, "status": payload.status})
    return serialize_doc(await db["lands"].find_one({"_id": land["_id"]}))


@router.post("/{land_id}/transfers", status_code=status.HTTP_201_CREATED, response_model=TransferOut, summary="Demander le transfert à un nouveau propriétaire")
async def request_transfer(
    land_id: str,
    payload: TransferRequest,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    land = await service.get_land_or_404(db, land_id)
    service.ensure_owner(land, user)
    if payload.new_owner_npi == user.npi:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Le nouveau propriétaire doit être une autre personne.")
    if land["dispute_flag"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Parcelle en litige : transfert impossible pour le moment.")
    if await db["transfers"].count_documents({"land_id": land_id, "status": "en_attente"}):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un transfert est déjà en attente pour cette parcelle.")
    now = utcnow()
    doc = {
        **payload.model_dump(), "land_id": land_id, "from_npi": user.npi, "status": "en_attente",
        "department": land["department"], "commune": land["commune"], "created_at": now, "updated_at": now,
    }
    res = await db["transfers"].insert_one(doc)
    doc["_id"] = res.inserted_id
    await notify(db, [payload.new_owner_npi], "transfer_requested", "Parcelle en cours de transfert",
                 f"Une parcelle de {land['surface_hectares']} ha à {land['commune']} va vous être transférée, après validation par un agent.",
                 {"transfer_id": str(res.inserted_id), "land_id": land_id})
    return serialize_doc(doc)


@router.get("/{land_id}/transfers", response_model=list[TransferOut])
async def land_transfers(land_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await service.get_land_or_404(db, land_id)
    service.ensure_owner_or_agent(land, user)
    cursor = db["transfers"].find({"land_id": land_id}).sort("created_at", -1)
    return [serialize_doc(d) async for d in cursor]


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
