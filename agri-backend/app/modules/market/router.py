import re
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.core.database import get_database
from app.core.security import CurrentUser, require_roles
from app.core.utils import serialize_doc, utcnow
from app.modules.market.schemas import HarvestOfferCreate, HarvestOfferOut

router = APIRouter(prefix="/market", tags=["Marché Agricole"])


@router.post("/offers", status_code=status.HTTP_201_CREATED)
async def publish_offer(
    offer: HarvestOfferCreate,
    db=Depends(get_database),
    user: CurrentUser = Depends(require_roles("farmer")),
):
    doc = {**offer.model_dump(), "farmer_npi": user.npi, "status": "active", "created_at": utcnow()}
    res = await db["market_offers"].insert_one(doc)
    return {"id": str(res.inserted_id), "status": "published"}


@router.get("/offers", response_model=list[HarvestOfferOut])
async def list_market_offers(
    db=Depends(get_database),
    commune: Optional[str] = Query(None, max_length=60),
    product: Optional[str] = Query(None, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    filters: dict = {"status": "active"}
    if commune:
        filters["location_commune"] = {"$regex": f"^{re.escape(commune)}$", "$options": "i"}
    if product:
        filters["product_name"] = {"$regex": re.escape(product), "$options": "i"}

    cursor = db["market_offers"].find(filters).sort("created_at", -1).skip(skip).limit(limit)
    return [serialize_doc(item) async for item in cursor]
