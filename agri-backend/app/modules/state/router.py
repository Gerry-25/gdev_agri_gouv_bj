from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.database import get_database
from app.core.security import CurrentUser, require_roles
from app.modules.monitoring.schemas import HealthStatus

router = APIRouter(prefix="/state", tags=["Espace Régulation & État"])


@router.get("/dashboard-metrics")
async def get_state_metrics(
    db=Depends(get_database),
    _: CurrentUser = Depends(require_roles("state_agent")),
):
    total_parcels = await db["lands"].count_documents({})
    # Seuls les diagnostics non sains comptent comme menaces
    total_threats = await db["phytosanitary_alerts"].count_documents(
        {"health_status": {"$ne": HealthStatus.SAIN.value}}
    )

    pipeline = [
        {"$match": {"status": "active"}},
        {"$group": {"_id": None, "total_value": {"$sum": {"$multiply": ["$quantity_kg", "$unit_price_fcfa"]}}}},
    ]
    total_market_val = 0
    async for res in db["market_offers"].aggregate(pipeline):
        total_market_val = res.get("total_value", 0)

    return {
        "parcels_monitored": total_parcels,
        "active_phytosanitary_threats": total_threats,
        "market_volume_fcfa": total_market_val,
        "potential_state_revenue_fcfa": round(total_market_val * settings.STATE_REVENUE_RATE, 2),
        "revenue_rate": settings.STATE_REVENUE_RATE,
    }
