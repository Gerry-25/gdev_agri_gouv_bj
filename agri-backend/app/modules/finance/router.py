import logging
from typing import Any, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, require_roles
from app.core.utils import parse_object_id, serialize_doc, utcnow
from app.modules.finance.schemas import (
    ApplicationCreate,
    ApplicationDecision,
    ApplicationDisbursement,
    ApplicationOut,
    FinanceStatsOut,
    OfferCreate,
    OfferOut,
)
from app.modules.finance.service import (
    evaluate_application_with_ai,
    get_farmer_profile_context,
)
from app.modules.notifications.service import notify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/finance", tags=["Finance Agricole, Crédit & Assurance"])


# ============================================================================
# OFFRES FINANCIÈRES (CATALOGUE)
# ============================================================================

@router.get("/offers", response_model=list[OfferOut], summary="Catalogue des offres financières")
async def list_offers(
    type_filter: Optional[str] = Query(None, alias="type", description="Filtrer par type (credit, assurance, financement)"),
    department: Optional[str] = Query(None, description="Filtrer par département éligible"),
    crop: Optional[str] = Query(None, description="Filtrer par culture ciblée"),
    db=Depends(get_database),
):
    """Consulte le catalogue des offres de crédit, d'assurance indicielle et de subventions ouvertes."""
    query: dict[str, Any] = {"active": True}
    if type_filter:
        query["type"] = type_filter
    if department:
        query["$or"] = [
            {"eligible_departments": {"$size": 0}},
            {"eligible_departments": department},
        ]
    if crop:
        query["$or"] = [
            {"eligible_crops": {"$size": 0}},
            {"eligible_crops": crop},
        ]

    cursor = db["financial_offers"].find(query).sort("created_at", -1)
    return [serialize_doc(doc) async for doc in cursor]


@router.get("/offers/{offer_id}", response_model=OfferOut, summary="Détail d'une offre financière")
async def get_offer_detail(
    offer_id: str,
    db=Depends(get_database),
):
    """Retourne la fiche détaillée d'une offre financière."""
    oid = parse_object_id(offer_id, "Offre financière")
    doc = await db["financial_offers"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offre financière introuvable.")
    return serialize_doc(doc)


@router.post("/offers", response_model=OfferOut, status_code=status.HTTP_201_CREATED, summary="Créer une offre financière (Agents/Superviseurs)")
async def create_offer(
    payload: OfferCreate,
    db=Depends(get_database),
    user: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    """Publie une nouvelle offre de crédit, assurance ou financement dans le catalogue officiel."""
    now = utcnow()
    doc = {
        **payload.model_dump(),
        "created_by": user.npi,
        "created_at": now,
        "updated_at": now,
    }
    res = await db["financial_offers"].insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize_doc(doc)


# ============================================================================
# CANDIDATURES (EXPLOITANTS)
# ============================================================================

@router.post("/applications", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED, summary="Postuler à une offre financière (Exploitant)")
async def submit_application(
    payload: ApplicationCreate,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    """L'exploitant soumet un dossier de crédit, d'assurance ou de subvention.

    Une évaluation automatique du profil et du risque par IA est générée immédiatement.
    """
    # 1. Vérification de l'offre
    oid = parse_object_id(payload.offer_id, "Offre financière")
    offer = await db["financial_offers"].find_one({"_id": oid, "active": True})
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offre financière introuvable ou inactive.")

    if payload.amount_requested < offer["amount_min"] or payload.amount_requested > offer["amount_max"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Le montant demandé ({payload.amount_requested:,.0f} FCFA) doit être compris entre {offer['amount_min']:,.0f} et {offer['amount_max']:,.0f} FCFA.",
        )

    # 2. Localisation et contexte parcelle
    user_doc = await db["users"].find_one({"npi": user.npi}) or {}
    farmer_name = user_doc.get("full_name") or "Exploitant"
    farmer_phone = user_doc.get("phone") or ""
    department = user_doc.get("department") or "Ouémé"
    commune = user_doc.get("commune") or "Dangbo"
    land_title = None

    if payload.land_id:
        try:
            lid = parse_object_id(payload.land_id, "Parcelle")
            land = await db["lands"].find_one({"_id": lid})
            if land:
                land_title = land.get("title")
                department = land.get("department", department)
                commune = land.get("commune", commune)
        except Exception:
            pass

    # 3. Récupération du contexte exploitant & Analyse IA
    farmer_ctx = await get_farmer_profile_context(db, user.npi)
    ai_evaluation = await evaluate_application_with_ai(db, offer, payload, farmer_ctx, user.npi)

    now = utcnow()
    doc = {
        "offer_id": str(offer["_id"]),
        "offer_title": offer["title"],
        "offer_type": offer["type"],
        "offer_institution": offer["institution"],
        "farmer_npi": user.npi,
        "farmer_name": farmer_name,
        "farmer_phone": farmer_phone,
        "department": department,
        "commune": commune,
        "land_id": payload.land_id,
        "land_title": land_title,
        "crop_type": payload.crop_type,
        "surface_ha": payload.surface_ha,
        "amount_requested": payload.amount_requested,
        "amount_approved": None,
        "project_description": payload.project_description,
        "declared_harvest_estimate_kg": payload.declared_harvest_estimate_kg,
        "guarantees_or_notes": payload.guarantees_or_notes,
        "status": "soumis",
        "ai_evaluation": ai_evaluation.model_dump(),
        "agent_decision": None,
        "disbursement": None,
        "created_at": now,
        "updated_at": now,
    }

    res = await db["financial_applications"].insert_one(doc)
    doc["_id"] = res.inserted_id

    # Notification aux agents du secteur
    agents = [a["npi"] async for a in db["users"].find({"role": {"$in": ["state_agent", "state_supervisor"]}}, {"npi": 1})]
    if agents:
        await notify(
            db,
            agents,
            type_="finance_application",
            title=f"Nouvelle demande : {offer['title']}",
            message=f"{farmer_name} ({commune}, {department}) sollicite {payload.amount_requested:,.0f} FCFA pour {payload.crop_type}. Avis IA : {ai_evaluation.verdict_label}.",
            data={"application_id": str(res.inserted_id), "type": offer["type"], "score": ai_evaluation.score},
        )

    return serialize_doc(doc)


@router.get("/applications/me", response_model=list[ApplicationOut], summary="Mes demandes de financement (Exploitant)")
async def get_my_applications(
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    """Consulte l'historique et l'avancement des dossiers financiers de l'exploitant connecté."""
    cursor = db["financial_applications"].find({"farmer_npi": user.npi}).sort("created_at", -1)
    return [serialize_doc(doc) async for doc in cursor]


@router.get("/applications/{application_id}", response_model=ApplicationOut, summary="Consulter une demande de financement")
async def get_application_detail(
    application_id: str,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    """Détail d'un dossier avec rapport d'analyse IA et décision."""
    oid = parse_object_id(application_id, "Dossier financier")
    doc = await db["financial_applications"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier financier introuvable.")

    is_agent = user.role in ("state_agent", "state_supervisor")
    if doc["farmer_npi"] != user.npi and not is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès non autorisé à ce dossier.")

    return serialize_doc(doc)


# ============================================================================
# COCKPIT AGENTS & SUPERVISEURS (REVUE & VALIDATION)
# ============================================================================

@router.get("/applications", response_model=list[ApplicationOut], summary="Cockpit global des demandes (Agents/Superviseurs)")
async def list_all_applications(
    status_filter: Optional[str] = Query(None, alias="status", description="Filtrer par statut (soumis, approuve, rejete, debourse_actif)"),
    type_filter: Optional[str] = Query(None, alias="type", description="Filtrer par type (credit, assurance, financement)"),
    department: Optional[str] = Query(None, description="Filtrer par département"),
    commune: Optional[str] = Query(None, description="Filtrer par commune"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    """Vue cockpit globale des demandes de crédit, d'assurance et de financement à instruire."""
    filters: dict[str, Any] = {}
    if status_filter:
        filters["status"] = status_filter
    if type_filter:
        filters["offer_type"] = type_filter
    if department:
        filters["department"] = department
    if commune:
        filters["commune"] = commune

    cursor = db["financial_applications"].find(filters).sort("created_at", -1).skip(skip).limit(limit)
    return [serialize_doc(doc) async for doc in cursor]


@router.get("/stats", response_model=FinanceStatsOut, summary="Statistiques financières et d'octroi (Agents)")
async def get_finance_stats(
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    """Indicateurs clés du portefeuille de financement, crédits et garanties agricoles."""
    total = await db["financial_applications"].count_documents({})
    pending = await db["financial_applications"].count_documents({"status": {"$in": ["soumis", "analyse_ia"]}})
    approved = await db["financial_applications"].count_documents({"status": "approuve"})
    rejected = await db["financial_applications"].count_documents({"status": "rejete"})
    disbursed = await db["financial_applications"].count_documents({"status": "debourse_actif"})

    # Agrégations montants demandés / approuvés
    amount_pipeline = [
        {
            "$group": {
                "_id": None,
                "total_requested": {"$sum": "$amount_requested"},
                "total_approved": {"$sum": {"$ifNull": ["$amount_approved", 0.0]}},
            }
        }
    ]
    amounts = await db["financial_applications"].aggregate(amount_pipeline).to_list(1)
    tot_req = amounts[0]["total_requested"] if amounts else 0.0
    tot_app = amounts[0]["total_approved"] if amounts else 0.0

    # Répartition par type
    by_type_agg = await db["financial_applications"].aggregate([
        {"$group": {"_id": "$offer_type", "count": {"$sum": 1}}},
    ]).to_list(10)
    by_type = {item["_id"]: item["count"] for item in by_type_agg if item["_id"]}

    # Répartition par statut
    by_status_agg = await db["financial_applications"].aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]).to_list(10)
    by_status = {item["_id"]: item["count"] for item in by_status_agg if item["_id"]}

    # Répartition par département
    by_dept_agg = await db["financial_applications"].aggregate([
        {"$group": {"_id": "$department", "count": {"$sum": 1}}},
    ]).to_list(15)
    by_dept = {item["_id"]: item["count"] for item in by_dept_agg if item["_id"]}

    approval_rate = round(100.0 * (approved + disbursed) / total, 1) if total > 0 else 0.0

    return FinanceStatsOut(
        total_applications=total,
        pending_applications=pending,
        approved_applications=approved,
        rejected_applications=rejected,
        disbursed_applications=disbursed,
        total_amount_requested=tot_req,
        total_amount_approved=tot_app,
        by_type=by_type,
        by_status=by_status,
        by_department=by_dept,
        approval_rate_pct=approval_rate,
    )


@router.patch("/applications/{application_id}/decision", response_model=ApplicationOut, summary="Prendre une décision officielle (Agent/Superviseur)")
async def decide_application(
    application_id: str,
    payload: ApplicationDecision,
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    """Valider, ajuster ou rejeter une demande avec motivation et conditions fixées."""
    oid = parse_object_id(application_id, "Dossier financier")
    doc = await db["financial_applications"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier financier introuvable.")

    now = utcnow()
    amount_app = payload.amount_approved if payload.status == "approuve" else None
    if payload.status == "approuve" and amount_app is None:
        amount_app = doc["amount_requested"]

    agent_doc = await db["users"].find_one({"npi": agent.npi}) or {}
    agent_name = agent_doc.get("full_name") or "Agent de l'État"

    decision_doc = {
        "status": payload.status,
        "decided_by_npi": agent.npi,
        "decided_by_name": agent_name,
        "amount_approved": amount_app,
        "interest_rate_approved": payload.interest_rate_approved,
        "duration_approved_months": payload.duration_approved_months,
        "conditions": payload.conditions,
        "motivation_or_notes": payload.motivation_or_notes,
        "decided_at": now,
    }

    update_fields: dict[str, Any] = {
        "status": payload.status,
        "amount_approved": amount_app,
        "agent_decision": decision_doc,
        "updated_at": now,
    }

    await db["financial_applications"].update_one({"_id": oid}, {"$set": update_fields})
    updated = await db["financial_applications"].find_one({"_id": oid})

    # Notifier l'exploitant
    title = f"Décision sur votre demande : {doc['offer_title']}"
    if payload.status == "approuve":
        msg = f"Félicitations ! Votre demande a été approuvée pour un montant de {amount_app:,.0f} FCFA. {payload.motivation_or_notes}"
    else:
        msg = f"Votre demande a été refusée. Motif : {payload.motivation_or_notes}"

    await notify(
        db,
        [doc["farmer_npi"]],
        type_="finance_decision",
        title=title,
        message=msg,
        data={"application_id": str(oid), "status": payload.status, "amount_approved": amount_app},
    )

    return serialize_doc(updated)


@router.patch("/applications/{application_id}/disburse", response_model=ApplicationOut, summary="Marquer comme déboursé / contrat actif (Agent/Superviseur)")
async def disburse_application(
    application_id: str,
    payload: ApplicationDisbursement,
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    """Enregistre le versement des fonds ou l'activation de la police d'assurance."""
    oid = parse_object_id(application_id, "Dossier financier")
    doc = await db["financial_applications"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier financier introuvable.")

    if doc["status"] not in ("approuve", "debourse_actif"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seul un dossier préalablement approuvé peut être marqué comme déboursé ou actif.",
        )

    now = utcnow()
    ref = payload.contract_ref or f"AGRI-FIN-{str(oid)[-6:].upper()}"
    disbursement_doc = {
        "disbursed_at": now,
        "contract_ref": ref,
        "payment_reference": payload.payment_reference,
        "disbursed_by": agent.npi,
        "notes": payload.notes,
    }

    await db["financial_applications"].update_one(
        {"_id": oid},
        {"$set": {"status": "debourse_actif", "disbursement": disbursement_doc, "updated_at": now}},
    )
    updated = await db["financial_applications"].find_one({"_id": oid})

    await notify(
        db,
        [doc["farmer_npi"]],
        type_="finance_disbursed",
        title=f"Contrat actif / Fonds déboursés : {doc['offer_title']}",
        message=f"Le contrat réf. {ref} est actif. Vos fonds / couverture sont disponibles.",
        data={"application_id": str(oid), "contract_ref": ref},
    )

    return serialize_doc(updated)


@router.post("/applications/{application_id}/evaluate-ai", response_model=ApplicationOut, summary="Relancer l'évaluation IA (Agent/Superviseur)")
async def reevaluate_application(
    application_id: str,
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    """Force une ré-évaluation du risque avec les dernières données agronomiques à jour."""
    oid = parse_object_id(application_id, "Dossier financier")
    doc = await db["financial_applications"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier financier introuvable.")

    offer_oid = parse_object_id(doc["offer_id"], "Offre")
    offer = await db["financial_offers"].find_one({"_id": offer_oid})
    if not offer:
        offer = {
            "title": doc["offer_title"],
            "type": doc["offer_type"],
            "institution": doc["offer_institution"],
            "amount_min": 100000,
            "amount_max": 10000000,
        }

    app_payload = ApplicationCreate(
        offer_id=doc["offer_id"],
        land_id=doc.get("land_id"),
        crop_type=doc["crop_type"],
        surface_ha=doc["surface_ha"],
        amount_requested=doc["amount_requested"],
        project_description=doc["project_description"],
        declared_harvest_estimate_kg=doc.get("declared_harvest_estimate_kg"),
        guarantees_or_notes=doc.get("guarantees_or_notes"),
    )

    farmer_ctx = await get_farmer_profile_context(db, doc["farmer_npi"])
    ai_evaluation = await evaluate_application_with_ai(db, offer, app_payload, farmer_ctx, doc["farmer_npi"])

    now = utcnow()
    await db["financial_applications"].update_one(
        {"_id": oid},
        {"$set": {"ai_evaluation": ai_evaluation.model_dump(), "updated_at": now}},
    )
    updated = await db["financial_applications"].find_one({"_id": oid})
    return serialize_doc(updated)
