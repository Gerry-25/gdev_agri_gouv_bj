"""Conseiller de stockage : suivi des stocks, rappels de contrôle et conseil « vendre ou stocker »."""
import re
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.core import ai_service
from app.core.benin import CommuneField, DepartmentField
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, require_roles
from app.core.utils import CLIENT_REF_DESCRIPTION, CLIENT_REF_PATTERN, parse_object_id, serialize_doc, utcnow
from app.modules.lands.service import ensure_owner, get_land_or_404
from app.modules.notifications.service import notify
from app.modules.storage.risk import assess

router = APIRouter(prefix="/storage", tags=["Conseiller de stockage"])
Method = Literal["sac_hermetique", "sac_polypropylene", "grenier_traditionnel", "magasin_ventile", "fut_hermetique", "autre"]


class LotCreate(BaseModel):
    product: str = Field(..., min_length=2, max_length=60, examples=["Maïs"])
    quantity_kg: float = Field(..., gt=0)
    harvest_date: date
    storage_method: Method
    moisture_pct: Optional[float] = Field(None, ge=3, le=40, description="Humidité mesurée (humidimètre)")
    treatment: Optional[str] = Field(None, max_length=200, description="Produit de conservation utilisé (homologué)")
    land_id: Optional[str] = None
    department: Optional[DepartmentField] = None
    commune: Optional[CommuneField] = None
    client_ref: Optional[str] = Field(None, pattern=CLIENT_REF_PATTERN, description=CLIENT_REF_DESCRIPTION)


class CheckCreate(BaseModel):
    moisture_pct: Optional[float] = Field(None, ge=3, le=40)
    insects_seen: bool = False
    mold_seen: bool = False
    quantity_kg: Optional[float] = Field(None, ge=0, description="Quantité restante constatée")
    note: Optional[str] = Field(None, max_length=500)


class LotStatus(BaseModel):
    status: Literal["vendu", "consomme", "perdu", "transfere"]
    quantity_lost_kg: Optional[float] = Field(None, ge=0)


class StorageAdvice(BaseModel):
    simple_summary: str
    immediate_actions: list[str]
    check_schedule: str
    sell_or_store: Literal["vendre_maintenant", "vendre_en_partie", "stocker"]
    sell_or_store_reasoning: str
    warrantage_note: str = Field(..., description="Possibilité de warrantage auprès d'une institution financière, si pertinent")
    warnings: list[str]


def _out(lot: dict) -> dict:
    out = serialize_doc({k: v for k, v in lot.items() if k != "npi"})
    out["risk"] = assess(lot) if lot.get("status", "en_stock") == "en_stock" else None
    return out


async def _lot(db, lot_id: str, user: CurrentUser) -> dict:
    lot = await db["stock_lots"].find_one({"_id": parse_object_id(lot_id, "Stock")})
    if not lot or (lot["npi"] != user.npi and not user.is_agent):
        raise HTTPException(status_code=404, detail="Stock introuvable.")
    return lot


@router.post("/lots", status_code=201, summary="Déclarer un stock")
async def create_lot(payload: LotCreate, response: Response, db=Depends(get_database), user: CurrentUser = Depends(require_roles("farmer"))):
    if payload.client_ref and (dup := await db["stock_lots"].find_one({"npi": user.npi, "client_ref": payload.client_ref})):
        response.status_code = status.HTTP_200_OK
        return _out(dup)
    doc = payload.model_dump(mode="json", exclude_none=True)
    if payload.land_id:
        land = await get_land_or_404(db, payload.land_id)
        ensure_owner(land, user)
        doc["department"], doc["commune"] = land["department"], land["commune"]
    if not doc.get("department"):
        profile = await db["users"].find_one({"npi": user.npi}) or {}
        doc["department"], doc["commune"] = profile.get("department"), profile.get("commune")
    doc.update({"npi": user.npi, "initial_quantity_kg": payload.quantity_kg, "status": "en_stock", "checks": [],
                "last_moisture_pct": payload.moisture_pct, "created_at": utcnow(), "updated_at": utcnow()})
    try:
        doc["_id"] = (await db["stock_lots"].insert_one(doc)).inserted_id
    except DuplicateKeyError:
        response.status_code = status.HTTP_200_OK
        return _out(await db["stock_lots"].find_one({"npi": user.npi, "client_ref": payload.client_ref}))
    return _out(doc)


@router.get("/lots/me", summary="Mes stocks, avec le risque et les contrôles à faire")
async def my_lots(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    lots = [l async for l in db["stock_lots"].find({"npi": user.npi}).sort("created_at", -1)]
    today = date.today().isoformat()
    for lot in lots:
        if lot["status"] != "en_stock":
            continue
        risk = assess(lot)
        # Rappel de contrôle créé une seule fois par échéance
        if risk["next_check_date"] <= today and lot.get("reminded_for") != risk["next_check_date"]:
            await notify(db, [user.npi], "storage_check", "Contrôle de votre stock",
                         f"Vérifiez votre stock de {lot['product']} : humidité, insectes, moisissures.", {"lot_id": str(lot["_id"])})
            await db["stock_lots"].update_one({"_id": lot["_id"]}, {"$set": {"reminded_for": risk["next_check_date"]}})
    return [_out(l) for l in lots]


@router.post("/lots/{lot_id}/checks", summary="Enregistrer un contrôle du stock")
async def add_check(lot_id: str, payload: CheckCreate, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    lot = await _lot(db, lot_id, user)
    if lot["status"] != "en_stock":
        raise HTTPException(status_code=409, detail="Ce stock n'est plus en cours.")
    check = {**payload.model_dump(), "date": date.today().isoformat()}
    changes = {"last_check_date": check["date"], "insects_seen": payload.insects_seen, "mold_seen": payload.mold_seen, "updated_at": utcnow()}
    if payload.moisture_pct is not None:
        changes["last_moisture_pct"] = payload.moisture_pct
    if payload.quantity_kg is not None:
        changes["quantity_kg"] = payload.quantity_kg
    await db["stock_lots"].update_one({"_id": lot["_id"]}, {"$set": changes, "$push": {"checks": check}})
    return _out(await db["stock_lots"].find_one({"_id": lot["_id"]}))


@router.patch("/lots/{lot_id}/status", summary="Clore un stock (vendu, consommé, perdu)")
async def close_lot(lot_id: str, payload: LotStatus, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    lot = await _lot(db, lot_id, user)
    lost = payload.quantity_lost_kg or (lot["quantity_kg"] if payload.status == "perdu" else 0)
    await db["stock_lots"].update_one({"_id": lot["_id"]}, {"$set": {
        "status": payload.status, "quantity_lost_kg": lost, "closed_at": utcnow(), "updated_at": utcnow()}})
    return _out(await db["stock_lots"].find_one({"_id": lot["_id"]}))


async def _price_trend(db, product: str, department: str | None) -> dict:
    """Prix observés sur la plateforme : 30 derniers jours contre les 60 précédents."""
    now = utcnow()

    async def avg(since, until):
        rows = [r async for r in db["market_offers"].aggregate([
            {"$match": {"product_name": {"$regex": f"^{re.escape(product)}", "$options": "i"}, "created_at": {"$gte": since, "$lt": until},
                        "status": {"$in": ["active", "sold"]}, **({"department": department} if department else {})}},
            {"$group": {"_id": None, "v": {"$avg": "$unit_price_fcfa"}, "n": {"$sum": 1}}}])]
        return (round(rows[0]["v"]), rows[0]["n"]) if rows and rows[0]["v"] is not None else (None, 0)

    recent, n1 = await avg(now - timedelta(days=30), now)
    before, n2 = await avg(now - timedelta(days=90), now - timedelta(days=30))
    trend = None if not (recent and before) else "hausse" if recent > before * 1.05 else "baisse" if recent < before * 0.95 else "stable"
    return {"recent_avg_fcfa_kg": recent, "previous_avg_fcfa_kg": before, "trend": trend, "observations": n1 + n2}


@router.post("/lots/{lot_id}/advice", summary="Conseil personnalisé : conservation, vendre ou stocker (IA)")
async def advice(lot_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    lot = await _lot(db, lot_id, user)
    risk = assess(lot)
    context = {
        "stock": {k: lot.get(k) for k in ("product", "quantity_kg", "initial_quantity_kg", "harvest_date", "storage_method",
                                          "last_moisture_pct", "treatment", "department", "commune")},
        "controles": lot.get("checks", [])[-5:], "risque_calcule": risk,
        "prix_sur_la_plateforme": await _price_trend(db, lot["product"], lot.get("department")),
    }
    prompt = ("Conseille un petit exploitant béninois sur la conservation de son stock et sur le choix vendre ou stocker. "
              "Actions concrètes et peu coûteuses (séchage, sacs hermétiques, tri, nettoyage du magasin). N'utilise jamais "
              "de pesticide non homologué pour la conservation. Si les prix sont en hausse et le risque faible, stocker peut "
              "se justifier ; si le risque est élevé, privilégie la vente ou la transformation. Mentionne le warrantage "
              "seulement s'il est pertinent.\n" + ai_service.to_prompt_json(context))
    out, run_id = await ai_service.generate(db, purpose="storage_advice", schema=StorageAdvice, prompt=prompt, requested_by=user.npi)
    res = {**out.model_dump(), "risk": risk, "prices": context["prix_sur_la_plateforme"], **ai_service.ai_meta(run_id)}
    await db["stock_lots"].update_one({"_id": lot["_id"]}, {"$set": {"last_advice": res}})
    return res


@router.get("/overview", summary="Stocks et pertes déclarés (agents)")
async def overview(db=Depends(get_database), _: CurrentUser = Depends(require_roles("state_agent"))):
    rows = [r async for r in db["stock_lots"].aggregate([
        {"$group": {"_id": {"product": {"$toLower": "$product"}, "department": "$department"},
                    "in_stock_kg": {"$sum": {"$cond": [{"$eq": ["$status", "en_stock"]}, "$quantity_kg", 0]}},
                    "lost_kg": {"$sum": {"$ifNull": ["$quantity_lost_kg", 0]}},
                    "initial_kg": {"$sum": "$initial_quantity_kg"}, "lots": {"$sum": 1}}}])]
    return [{**r["_id"], **{k: v for k, v in r.items() if k != "_id"},
             "loss_rate_pct": round(100 * r["lost_kg"] / r["initial_kg"], 1) if r["initial_kg"] else 0} for r in rows]
