from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core import geo
from app.core.config import settings
from app.core.database import get_database
from app.core.security import CurrentUser, require_roles
from app.core.utils import utcnow
from app.modules.lands.router import land_feature
from app.modules.lands.schemas import OPEN_DISPUTE_STATUSES
from app.modules.monitoring.schemas import HealthStatus

# Toutes les routes de ce module sont réservées aux agents de l'État
router = APIRouter(
    prefix="/state",
    tags=["Espace Régulation & État"],
    dependencies=[Depends(require_roles("state_agent"))],
)

_THREAT = {"health_status": {"$ne": HealthStatus.SAIN.value}}


async def _aggregate(coll, pipeline: list) -> list[dict]:
    return [d async for d in coll.aggregate(pipeline)]


async def _sum(coll, match: dict, expr) -> float:
    rows = await _aggregate(coll, [{"$match": match}, {"$group": {"_id": None, "v": {"$sum": expr}}}])
    return rows[0]["v"] if rows else 0


def _bbox_or_422(bbox: str) -> dict:
    try:
        return geo.bbox_polygon(bbox)
    except geo.GeometryError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/dashboard-metrics", summary="Indicateurs nationaux")
async def get_state_metrics(db=Depends(get_database), days: int = Query(30, ge=1, le=365)):
    since = utcnow() - timedelta(days=days)
    rate = settings.STATE_REVENUE_RATE
    offers = db["market_offers"]

    active_value = await _sum(offers, {"status": "active"}, {"$multiply": ["$quantity_kg", "$unit_price_fcfa"]})
    sold_value = await _sum(offers, {"status": "sold"}, {"$multiply": ["$sold_quantity_kg", "$sold_unit_price_fcfa"]})

    return {
        "parcels_monitored": await db["lands"].count_documents({}),
        "surface_total_ha": round(await _sum(db["lands"], {}, "$surface_hectares"), 2),
        "estimated_production_kg": await _sum(db["lands"], {}, "$estimated_yield_kg"),
        "actual_production_kg": await _sum(db["harvests"], {}, "$actual_yield_kg"),
        "open_disputes": await db["disputes"].count_documents({"status": {"$in": OPEN_DISPUTE_STATUSES}}),
        "pending_transfers": await db["transfers"].count_documents({"status": "en_attente"}),
        "parcels_verified": await db["lands"].count_documents({"verification_status": "verifiee"}),
        "parcels_awaiting_verification": await db["lands"].count_documents({"verification_status": {"$in": ["declaree", None]}}),
        "registered_farmers": await db["users"].count_documents({"role": "farmer"}),
        "registered_buyers": await db["users"].count_documents({"role": "buyer"}),
        "phytosanitary_threats_total": await db["phytosanitary_alerts"].count_documents(_THREAT),
        f"phytosanitary_threats_last_{days}_days": await db["phytosanitary_alerts"].count_documents({**_THREAT, "observed_at": {"$gte": since}}),
        "market_active_volume_fcfa": active_value,
        "market_sold_volume_fcfa": sold_value,
        "state_domains_total": await db["state_domains"].count_documents({"status": {"$ne": "retire"}}),
        "state_domains_surface_ha": round(await _sum(db["state_domains"], {"status": {"$ne": "retire"}}, "$surface_hectares"), 2),
        "state_domains_attributed": await db["state_domains"].count_documents({"status": "attribue"}),
        "calls_open": await db["calls"].count_documents({"status": "publie"}),
        "concessions_active": await db["concessions"].count_documents({"status": "active"}),
        "concession_fees_collected_fcfa": (await _aggregate(db["concessions"], [
            {"$unwind": "$payments"}, {"$group": {"_id": None, "v": {"$sum": "$payments.amount_fcfa"}}}]) or [{"v": 0}])[0]["v"],
        "revenue_rate": rate,
        "revenue_from_declared_sales_fcfa": round(sold_value * rate, 2),
        "revenue_potential_active_offers_fcfa": round(active_value * rate, 2),
    }


@router.get("/stats/zones", summary="Surfaces, production et menaces par département ou commune")
async def stats_by_zone(
    db=Depends(get_database),
    level: Literal["department", "commune"] = "department",
    department: Optional[str] = Query(None, description="Restreindre à un département (utile avec level=commune)"),
    days: int = Query(30, ge=1, le=365),
):
    keys = {"department": "$department"} if level == "department" else {"department": "$department", "commune": "$commune"}
    base = {"department": department} if department else {}

    lands = await _aggregate(db["lands"], [
        {"$match": base},
        {"$group": {"_id": keys, "parcels": {"$sum": 1}, "surface_ha": {"$sum": "$surface_hectares"},
                    "estimated_production_kg": {"$sum": "$estimated_yield_kg"},
                    "parcels_in_dispute": {"$sum": {"$cond": ["$dispute_flag", 1, 0]}}}},
    ])
    harvests = await _aggregate(db["harvests"], [
        {"$match": base}, {"$group": {"_id": keys, "actual_production_kg": {"$sum": "$actual_yield_kg"}}},
    ])
    threats = await _aggregate(db["phytosanitary_alerts"], [
        {"$match": {**base, **_THREAT, "observed_at": {"$gte": utcnow() - timedelta(days=days)}}},
        {"$group": {"_id": keys, "threats": {"$sum": 1},
                    "critical": {"$sum": {"$cond": [{"$eq": ["$severity", "Critique"]}, 1, 0]}}}},
    ])

    zones: dict[tuple, dict] = {}
    def zone(k: dict) -> dict:
        t = tuple(k.get(f) for f in keys)
        return zones.setdefault(t, {**k, "parcels": 0, "surface_ha": 0, "estimated_production_kg": 0,
                                    "actual_production_kg": 0, "parcels_in_dispute": 0, "threats": 0, "critical": 0})
    for rows in (lands, harvests, threats):
        for r in rows:
            zone(r["_id"]).update({k: v for k, v in r.items() if k != "_id"})
    for z in zones.values():
        z["surface_ha"] = round(z["surface_ha"], 2)
    return sorted(zones.values(), key=lambda z: -z["surface_ha"])


@router.get("/stats/crops", summary="Surfaces et production (prévue / réelle) par culture")
async def stats_by_crop(db=Depends(get_database), department: Optional[str] = None):
    base = {"department": department} if department else {}
    lands = await _aggregate(db["lands"], [
        {"$match": base},
        {"$group": {"_id": "$crop_type", "parcels": {"$sum": 1}, "surface_ha": {"$sum": "$surface_hectares"},
                    "estimated_production_kg": {"$sum": "$estimated_yield_kg"}}},
    ])
    # Rendement = récolte totale / surface réellement récoltée (une parcelle compte une fois par saison récoltée)
    surfaces = {str(l["_id"]): l["surface_hectares"] async for l in db["lands"].find(base, {"surface_hectares": 1})}
    actual, harvested_ha, seasons = {}, {}, {}
    async for h in db["harvests"].find(base, {"crop_type": 1, "actual_yield_kg": 1, "land_id": 1, "season": 1}):
        c = h["crop_type"]
        actual[c] = actual.get(c, 0) + h["actual_yield_kg"]
        harvested_ha[c] = harvested_ha.get(c, 0) + surfaces.get(h["land_id"], 0)
        seasons.setdefault(c, set()).add(h["season"])
    out = []
    for r in lands:
        c = r["_id"]
        out.append({
            "crop_type": c, "parcels": r["parcels"], "surface_ha": round(r["surface_ha"], 2),
            "estimated_production_kg": r["estimated_production_kg"],
            "actual_production_kg": actual.get(c, 0),  # cumul de toutes les saisons déclarées
            "seasons": len(seasons.get(c, ())),
            "yield_kg_per_ha": round(actual[c] / harvested_ha[c], 1) if harvested_ha.get(c) else None,
        })
    return sorted(out, key=lambda c: -c["surface_ha"])


@router.get("/sanitary/hotspots", summary="Foyers phytosanitaires par commune et par maladie")
async def sanitary_hotspots(
    db=Depends(get_database),
    days: int = Query(30, ge=1, le=365),
    min_cases: Optional[int] = Query(None, ge=1, description=f"Seuil de cas pour un foyer (défaut : {settings.HOTSPOT_MIN_CASES})"),
    department: Optional[str] = None,
):
    threshold = min_cases or settings.HOTSPOT_MIN_CASES
    match = {**_THREAT, "observed_at": {"$gte": utcnow() - timedelta(days=days)}}
    if department:
        match["department"] = department
    rows = await _aggregate(db["phytosanitary_alerts"], [
        {"$match": match},
        {"$group": {
            "_id": {"department": "$department", "commune": "$commune", "disease": "$disease_name", "crop": "$crop_identified"},
            "cases": {"$sum": 1},
            "critical_cases": {"$sum": {"$cond": [{"$eq": ["$severity", "Critique"]}, 1, 0]}},
            "affected_farmers": {"$addToSet": "$farmer_npi"},
            "last_seen": {"$max": "$observed_at"},
        }},
        {"$sort": {"cases": -1}},
    ])
    out = []
    for r in rows:
        hotspot = r["cases"] >= threshold
        out.append({
            **r["_id"],
            "cases": r["cases"],
            "critical_cases": r["critical_cases"],
            "affected_farmers": len(r["affected_farmers"]),
            "last_seen": r["last_seen"],
            "is_hotspot": hotspot,
            "alert_level": "red" if hotspot and r["critical_cases"] else "orange" if hotspot else "yellow",
        })
    return {"period_days": days, "hotspot_threshold": threshold, "zones": out}


@router.get("/map/lands", summary="Parcelles en GeoJSON pour la carte nationale")
async def map_lands(
    db=Depends(get_database),
    bbox: Optional[str] = Query(None, description="Zone visible : lon_min,lat_min,lon_max,lat_max"),
    department: Optional[str] = None,
    commune: Optional[str] = None,
    crop_type: Optional[str] = None,
    dispute_only: bool = False,
    verification_status: Optional[str] = Query(None, description="declaree, verifiee ou rejetee"),
    limit: int = Query(2000, ge=1, le=10_000),
):
    filters: dict = {}
    if bbox:
        filters["boundary"] = {"$geoIntersects": {"$geometry": _bbox_or_422(bbox)}}
    for field, value in (("department", department), ("commune", commune), ("crop_type", crop_type)):
        if value:
            filters[field] = value
    if dispute_only:
        filters["dispute_flag"] = True
    if verification_status:
        filters["verification_status"] = verification_status
    cursor = db["lands"].find(filters, {"boundary_history": 0}).limit(limit)
    return geo.feature_collection([land_feature(d) async for d in cursor])


@router.get("/map/alerts", summary="Diagnostics localisés en GeoJSON (points) pour la carte sanitaire")
async def map_alerts(
    db=Depends(get_database),
    bbox: Optional[str] = Query(None, description="Zone visible : lon_min,lat_min,lon_max,lat_max"),
    days: int = Query(30, ge=1, le=365),
    disease: Optional[str] = None,
    include_healthy: bool = False,
    limit: int = Query(5000, ge=1, le=20_000),
):
    filters: dict = {"location": {"$exists": True}, "observed_at": {"$gte": utcnow() - timedelta(days=days)}}
    if not include_healthy:
        filters.update(_THREAT)
    if disease:
        filters["disease_name"] = disease
    if bbox:
        filters["location"] = {"$geoWithin": {"$geometry": _bbox_or_422(bbox)}}
    cursor = db["phytosanitary_alerts"].find(filters).sort("observed_at", -1).limit(limit)
    features = [
        geo.feature(d["location"], {
            "id": str(d["_id"]), "disease_name": d.get("disease_name"), "crop": d.get("crop_identified"),
            "severity": d.get("severity"), "alert_color": d.get("alert_color"), "health_status": d.get("health_status"),
            "department": d.get("department"), "commune": d.get("commune"), "observed_at": d["observed_at"].isoformat(),
        })
        async for d in cursor
    ]
    return geo.feature_collection(features)
