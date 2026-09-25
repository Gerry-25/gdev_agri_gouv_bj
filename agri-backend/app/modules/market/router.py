import re
from datetime import timedelta
from typing import Optional
from urllib.parse import quote

import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.core import ai_service
from app.core.config import settings
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, get_optional_user, require_roles
from app.core.utils import parse_object_id, serialize_doc, utcnow
from app.modules.lands.service import ensure_owner, get_land_or_404
from app.modules.market.schemas import (
    HarvestOfferCreate,
    HarvestOfferOut,
    HarvestOfferUpdate,
    InterestCreate,
    InterestOut,
    OfferStatusUpdate,
)
from app.modules.notifications.service import notify

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
    response: Response,
    db=Depends(get_database),
    user: CurrentUser = Depends(require_roles("farmer")),
):
    async def already_published():
        if offer.client_ref:
            existing = await db["market_offers"].find_one({"farmer_npi": user.npi, "client_ref": offer.client_ref})
            if existing:
                response.status_code = status.HTTP_200_OK
                return offer_out(existing)
        return None

    if (dup := await already_published()) is not None:
        return dup
    doc = offer.model_dump(mode="json", exclude_none=True)
    if offer.land_id:
        land = await get_land_or_404(db, offer.land_id)
        ensure_owner(land, user)
        doc["location_commune"], doc["department"] = land["commune"], land["department"]

    now = utcnow()
    doc.update({"farmer_npi": user.npi, "status": "active", "interest_count": 0, "created_at": now, "updated_at": now})
    try:
        res = await db["market_offers"].insert_one(doc)
    except DuplicateKeyError:
        if (dup := await already_published()) is not None:
            return dup
        raise
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
            raise HTTPException(status_code=422, detail="La quantité vendue dépasse la quantité proposée.")
        changes.update({
            "sold_quantity_kg": sold_qty,
            "sold_unit_price_fcfa": payload.sold_unit_price_fcfa or doc["unit_price_fcfa"],
            "sold_at": now,
        })
    await db["market_offers"].update_one({"_id": doc["_id"]}, {"$set": changes})
    return offer_out(await db["market_offers"].find_one({"_id": doc["_id"]}))


@router.post("/offers/{offer_id}/interest", status_code=status.HTTP_201_CREATED, response_model=InterestOut,
             summary="Signaler son intérêt au producteur (il est notifié)")
async def express_interest(
    offer_id: str,
    payload: InterestCreate,
    response: Response,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    offer = await _get_offer_or_404(db, offer_id)
    if offer["status"] != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cette offre n'est plus disponible.")
    if offer["farmer_npi"] == user.npi:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="C'est votre propre offre.")

    buyer = await db["users"].find_one({"npi": user.npi}) or {}
    doc = {**payload.model_dump(), "offer_id": offer_id, "buyer_npi": user.npi, "created_at": utcnow()}
    try:
        res = await db["offer_interests"].insert_one(doc)
    except DuplicateKeyError:
        response.status_code = status.HTTP_200_OK  # intérêt déjà signalé : pas de nouvelle notification
        existing = await db["offer_interests"].find_one({"offer_id": offer_id, "buyer_npi": user.npi})
        return {**serialize_doc(existing), "buyer_name": buyer.get("full_name"), "buyer_phone": buyer.get("phone")}

    await db["market_offers"].update_one({"_id": offer["_id"]}, {"$inc": {"interest_count": 1}})
    qty = f" pour {_fmt(payload.quantity_kg)} kg" if payload.quantity_kg else ""
    await notify(db, [offer["farmer_npi"]], "offer_interest", "Un acheteur est intéressé",
                 f"{buyer.get('full_name', 'Un acheteur')} est intéressé(e) par votre offre {offer['product_name']}{qty}.",
                 {"offer_id": offer_id, "buyer_phone": buyer.get("phone")})
    doc["_id"] = res.inserted_id
    return {**serialize_doc(doc), "buyer_name": buyer.get("full_name"), "buyer_phone": buyer.get("phone")}


@router.get("/offers/{offer_id}/interests", response_model=list[InterestOut], summary="Acheteurs intéressés par mon offre")
async def list_interests(offer_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    offer = await _get_offer_or_404(db, offer_id)
    if offer["farmer_npi"] != user.npi and not user.is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")
    interests = [d async for d in db["offer_interests"].find({"offer_id": offer_id}).sort("created_at", -1)]
    buyers = {u["npi"]: u async for u in db["users"].find({"npi": {"$in": [i["buyer_npi"] for i in interests]}})}
    return [
        {**serialize_doc(i), "buyer_name": buyers.get(i["buyer_npi"], {}).get("full_name"), "buyer_phone": buyers.get(i["buyer_npi"], {}).get("phone")}
        for i in interests
    ]


@router.get("/prices", summary="Prix de référence par produit et département (FCFA/kg)")
async def reference_prices(
    db=Depends(get_database),
    product: Optional[str] = Query(None, max_length=100),
    department: Optional[str] = Query(None, max_length=60),
    days: int = Query(90, ge=7, le=730),
):
    match: dict = {"created_at": {"$gte": utcnow() - timedelta(days=days)}, "status": {"$in": ["active", "sold"]}}
    if product:
        match["product_name"] = {"$regex": re.escape(product), "$options": "i"}
    if department:
        match["department"] = {"$regex": f"^{re.escape(department)}$", "$options": "i"}

    rows = [r async for r in db["market_offers"].aggregate([
        {"$match": match},
        {"$project": {
            "product": {"$toLower": "$product_name"}, "department": 1, "status": 1,
            # Pour une vente : prix réellement obtenu ; sinon : prix demandé
            "price": {"$cond": [{"$eq": ["$status", "sold"]}, "$sold_unit_price_fcfa", "$unit_price_fcfa"]},
        }},
        {"$group": {
            "_id": {"product": "$product", "department": "$department", "status": "$status"},
            "avg": {"$avg": "$price"}, "min": {"$min": "$price"}, "max": {"$max": "$price"}, "n": {"$sum": 1},
        }},
    ])]
    out: dict[tuple, dict] = {}
    for r in rows:
        k = (r["_id"]["product"], r["_id"].get("department"))
        entry = out.setdefault(k, {"product": k[0], "department": k[1], "sold": None, "offered": None})
        entry["sold" if r["_id"]["status"] == "sold" else "offered"] = {
            "avg": round(r["avg"]), "min": round(r["min"]), "max": round(r["max"]), "count": r["n"],
        }
    return {"period_days": days, "prices": sorted(out.values(), key=lambda e: (e["product"], e["department"] or ""))}


async def _price_basis(db, product: str, department: Optional[str], days: int = 90) -> dict:
    """Base de prix déterministe : prix de vente constatés en priorité, sinon prix demandés."""
    since = utcnow() - timedelta(days=days)
    match = {"created_at": {"$gte": since}, "product_name": {"$regex": re.escape(product), "$options": "i"}, "status": {"$in": ["active", "sold"]}}
    for scope, extra in (("departement", {"department": department} if department else None), ("national", {})):
        if extra is None:
            continue
        rows = [r async for r in db["market_offers"].aggregate([
            {"$match": {**match, **extra}},
            {"$group": {"_id": "$status", "avg": {"$avg": {"$cond": [{"$eq": ["$status", "sold"]}, "$sold_unit_price_fcfa", "$unit_price_fcfa"]}},
                        "n": {"$sum": 1}}}])]
        by = {r["_id"]: r for r in rows}
        ref = by.get("sold") or by.get("active")
        if ref and ref["n"] >= 2:
            avg = ref["avg"]
            return {"scope": scope, "basis": "ventes constatées" if "sold" in by else "prix demandés", "observations": ref["n"],
                    "suggested_min_fcfa_kg": round(avg * 0.9, -1), "suggested_max_fcfa_kg": round(avg * 1.1, -1), "reference_avg_fcfa_kg": round(avg)}
    return {"scope": None, "basis": "pas assez de données sur la plateforme", "observations": 0}


@router.get("/price-suggestion", summary="Fourchette de prix conseillée avant de publier (sans IA)")
async def price_suggestion(db=Depends(get_database), product: str = Query(..., min_length=2, max_length=100),
                           department: Optional[str] = Query(None, max_length=60)):
    return await _price_basis(db, product, department)


class OfferDraft(BaseModel):
    product_name: str
    quality_description: str = Field(..., description="Qualité visible et déclarée, sans exagération")
    listing_text: str = Field(..., description="Texte d'annonce court et clair (3 phrases maximum)")
    quality_warnings: list[str] = Field(default_factory=list, description="Défauts visibles à signaler honnêtement")


@router.post("/offers/ai-draft", summary="Rédiger une annonce à partir d'une photo et de quelques mots (IA)")
async def offer_draft(
    notes: str = Form(..., min_length=3, max_length=500, description="Ex. : maïs blanc bien sec, récolte d'août"),
    quantity_kg: Optional[float] = Form(None, gt=0),
    department: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db=Depends(get_database),
    user: CurrentUser = Depends(require_roles("farmer")),
):
    parts = []
    if file is not None:
        raw = await file.read(settings.max_upload_bytes + 1)
        if len(raw) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="Photo trop volumineuse.")
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        except (UnidentifiedImageError, OSError):
            raise HTTPException(status_code=400, detail="Image illisible.")
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=75)
        parts.append((buf.getvalue(), "image/jpeg"))
    prompt = ("Rédige une annonce de vente de récolte honnête pour un marché agricole béninois, à partir des notes du producteur"
              + (" et de la photo jointe" if parts else "") + ". N'invente aucune certification ni qualité non visible ; "
              f"signale les défauts visibles.\nNotes : {notes}\nQuantité : {quantity_kg or 'non précisée'} kg")
    draft, run_id = await ai_service.generate(db, purpose="offer_draft", schema=OfferDraft, prompt=prompt, parts=parts, requested_by=user.npi)
    return {**draft.model_dump(), "price": await _price_basis(db, draft.product_name.split()[0], department), **ai_service.ai_meta(run_id),
            "note": "Brouillon à relire : le prix et le texte restent à votre choix."}
