import re
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, get_optional_user, require_roles
from app.core.utils import parse_object_id, serialize_doc, utcnow
from app.modules.lands.service import ensure_owner, get_land_or_404
from app.modules.market.schemas import HarvestOfferCreate, HarvestOfferOut, HarvestOfferUpdate, OfferStatusUpdate

router = APIRouter(prefix="/market", tags=["Marché Agricole"])


def _fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", " ")


def offer_out(doc: dict) -> dict:
    out = serialize_doc(doc)
    digits = doc["contact_phone"].lstrip("+")
    message = (
        f"Bonjour, je suis intéressé(e) par votre offre AgriSmart : {doc['product_name']}, "
        f"{_fmt(doc['quantity_kg'])} kg à {_fmt(doc['unit_price_fcfa'])} FCFA/kg ({doc['location_commune']})."
    )
    out["tel_url"] = f"tel:{doc['contact_phone']}"
    out["whatsapp_url"] = f"https://wa.me/{digits}?text={quote(message)}"
    return out


async def _get_offer_or_404(db, offer_id: str) -> dict:
    doc = await db["market_offers"].find_one({"_id": parse_object_id(offer_id, "Offre")})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offre introuvable.")
    return doc


@router.post("/offers", status_code=status.HTTP_201_CREATED, response_model=HarvestOfferOut)
async def publish_offer(
    offer: HarvestOfferCreate,
    db=Depends(get_database),
    user: CurrentUser = Depends(require_roles("farmer")),
):
    doc = offer.model_dump(mode="json")
    if offer.land_id:
        land = await get_land_or_404(db, offer.land_id)
        ensure_owner(land, user)
        doc["location_commune"], doc["department"] = land["commune"], land["department"]

    now = utcnow()
    doc.update({"farmer_npi": user.npi, "status": "active", "created_at": now, "updated_at": now})
    res = await db["market_offers"].insert_one(doc)
    doc["_id"] = res.inserted_id
    return offer_out(doc)


@router.get("/offers", response_model=list[HarvestOfferOut], summary="Catalogue public des offres actives")
async def list_market_offers(
    db=Depends(get_database),
    commune: Optional[str] = Query(None, max_length=60),
    department: Optional[str] = Query(None, max_length=60),
    product: Optional[str] = Query(None, max_length=100),
    max_price: Optional[float] = Query(None, gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    filters: dict = {"status": "active"}
    if commune:
        filters["location_commune"] = {"$regex": f"^{re.escape(commune)}$", "$options": "i"}
    if department:
        filters["department"] = {"$regex": f"^{re.escape(department)}$", "$options": "i"}
    if product:
        filters["product_name"] = {"$regex": re.escape(product), "$options": "i"}
    if max_price:
        filters["unit_price_fcfa"] = {"$lte": max_price}
    cursor = db["market_offers"].find(filters).sort("created_at", -1).skip(skip).limit(limit)
    return [offer_out(d) async for d in cursor]


@router.get("/offers/me", response_model=list[HarvestOfferOut], summary="Mes offres (tous statuts)")
async def my_offers(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    cursor = db["market_offers"].find({"farmer_npi": user.npi}).sort("created_at", -1)
    return [offer_out(d) async for d in cursor]


@router.get("/offers/{offer_id}", response_model=HarvestOfferOut)
async def get_offer(offer_id: str, db=Depends(get_database), user: CurrentUser | None = Depends(get_optional_user)):
    doc = await _get_offer_or_404(db, offer_id)
    # Les offres vendues ou retirées ne sont visibles que par leur auteur et les agents
    if doc["status"] != "active" and not (user and (user.npi == doc["farmer_npi"] or user.is_agent)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offre introuvable.")
    return offer_out(doc)


@router.patch("/offers/{offer_id}", response_model=HarvestOfferOut)
async def update_offer(
    offer_id: str,
    payload: HarvestOfferUpdate,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    doc = await _get_offer_or_404(db, offer_id)
    if doc["farmer_npi"] != user.npi:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cette offre ne vous appartient pas.")
    if doc["status"] != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seule une offre active peut être modifiée.")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aucune modification fournie.")
    await db["market_offers"].update_one({"_id": doc["_id"]}, {"$set": {**changes, "updated_at": utcnow()}})
    return offer_out(await db["market_offers"].find_one({"_id": doc["_id"]}))


@router.patch("/offers/{offer_id}/status", response_model=HarvestOfferOut, summary="Marquer vendue, retirer ou réactiver")
async def update_offer_status(
    offer_id: str,
    payload: OfferStatusUpdate,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    doc = await _get_offer_or_404(db, offer_id)
    if doc["farmer_npi"] != user.npi:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cette offre ne vous appartient pas.")
    if doc["status"] == "sold":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Une offre vendue ne peut plus changer de statut.")
    if payload.status == doc["status"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="L'offre a déjà ce statut.")

    now = utcnow()
    changes: dict = {"status": payload.status, "updated_at": now}
    if payload.status == "sold":
        sold_qty = payload.sold_quantity_kg or doc["quantity_kg"]
        if sold_qty > doc["quantity_kg"]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="La quantité vendue dépasse la quantité proposée.")
        changes.update({
            "sold_quantity_kg": sold_qty,
            "sold_unit_price_fcfa": payload.sold_unit_price_fcfa or doc["unit_price_fcfa"],
            "sold_at": now,
        })
    await db["market_offers"].update_one({"_id": doc["_id"]}, {"$set": changes})
    return offer_out(await db["market_offers"].find_one({"_id": doc["_id"]}))
