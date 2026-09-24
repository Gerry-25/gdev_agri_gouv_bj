"""Routes du domaine privé agricole de l'État.

Procédure d'attribution par appel à candidatures :
  terre enregistrée (agent) → appel rédigé (agent) → publication (superviseur ≠ rédacteur)
  → candidatures (exploitants éligibles) → clôture → proposition d'attribution (agent, justifiée)
  → validation (superviseur ≠ auteur de la proposition) → délai de contestation (candidats)
  → acceptation (lauréat) → enregistrement de l'acte officiel (agent) → concession active
  → rapports de campagne, inspections, redevances → retrait ou fin (superviseur).
"""
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo.errors import DuplicateKeyError

from app.core import geo
from app.core.config import settings
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, require_roles
from app.core.utils import as_utc, serialize_doc, utcnow
from app.modules.domains import service as ds
from app.modules.domains.schemas import (
    AcceptanceInput,
    ApplicationCreate,
    ApplicationOut,
    AwardDecision,
    AwardProposal,
    CallCreate,
    CallOut,
    ConcessionReportCreate,
    ContestationCreate,
    ContestationDecision,
    ContestationOut,
    DomainCreate,
    DomainOut,
    DomainRegistrationResult,
    DomainUpdate,
    EligibilityOut,
    InspectionCreate,
    OfficialActInput,
    PaymentCreate,
    PublicCallOut,
    ReasonInput,
    TerminationInput,
)
from app.modules.lands import service as land_service
from app.modules.notifications.service import notify
from app.modules.performance.service import compute_scores

router = APIRouter()
AGENT = require_roles("state_agent")
SUPERVISOR = require_roles("state_supervisor")


def _history(action: str, by: str, note: str | None = None) -> dict:
    return {"action": action, "by": by, "note": note, "at": utcnow()}


def _four_eyes(user: CurrentUser, author: str, what: str) -> None:
    if user.npi == author:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"{what} doit être validé(e) par une autre personne que son auteur.")


# ================================================================================
# Terres du domaine privé de l'État
# ================================================================================

@router.post("/domains", status_code=status.HTTP_201_CREATED, response_model=DomainRegistrationResult, tags=["Domaine de l'État"])
async def register_domain(payload: DomainCreate, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    poly, info, warnings = land_service.geometry_from_boundary(payload.boundary)
    clash = await land_service.find_overlaps(db, poly, collection="state_domains")
    if clash:
        raise ds.conflict(f"Ce contour chevauche une terre de l'État déjà enregistrée : {clash[0]['land'].get('name')}.")

    now = utcnow()
    doc = {**payload.model_dump(mode="json", exclude={"boundary"}), **info, "status": "disponible", "dispute_flag": False,
           "current_call_id": None, "current_concession_id": None, "created_by": agent.npi, "created_at": now, "updated_at": now}
    res = await db["state_domains"].insert_one(doc)
    doc["_id"] = res.inserted_id

    overlaps = []
    for o in await land_service.find_overlaps(db, poly, collection="lands"):
        for d in await land_service.open_domain_disputes(db, o["land"], [{"land": doc, "overlap_m2": o["overlap_m2"]}]):
            overlaps.append({"land_id": str(o["land"]["_id"]), "domain_id": d["domain_id"], "overlap_m2": d["overlap_m2"], "dispute_id": d["dispute_id"]})
    if overlaps:
        warnings.append(f"{len(overlaps)} parcelle(s) privée(s) empiètent sur cette terre : des litiges ont été ouverts. "
                        "Aucun appel ne pourra être publié avant leur clôture.")
    return DomainRegistrationResult(id=str(res.inserted_id), surface_hectares=info["surface_hectares"],
                                    status="registered_with_dispute" if overlaps else "registered", overlaps=overlaps, warnings=warnings)


@router.get("/domains", response_model=list[DomainOut], tags=["Domaine de l'État"])
async def list_domains(
    db=Depends(get_database),
    _: CurrentUser = Depends(AGENT),
    domain_status: Optional[str] = Query(None, alias="status"),
    department: Optional[str] = None,
):
    filters = {k: v for k, v in (("status", domain_status), ("department", department)) if v}
    return [serialize_doc(d) async for d in db["state_domains"].find(filters).sort("created_at", -1)]


@router.get("/domains/geojson", tags=["Domaine de l'État"], summary="Terres de l'État en GeoJSON (carte des agents)")
async def domains_geojson(db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    features = [geo.feature(d["boundary"], {
        "id": str(d["_id"]), "name": d["name"], "status": d["status"], "department": d["department"], "commune": d["commune"],
        "surface_hectares": d["surface_hectares"], "dispute_flag": d["dispute_flag"],
    }) async for d in db["state_domains"].find({})]
    return geo.feature_collection(features)


@router.get("/domains/{domain_id}", response_model=DomainOut, tags=["Domaine de l'État"])
async def get_domain(domain_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    return serialize_doc(await ds.get_or_404(db, "state_domains", domain_id, "Terre de l'État"))


@router.patch("/domains/{domain_id}", response_model=DomainOut, tags=["Domaine de l'État"])
async def update_domain(domain_id: str, payload: DomainUpdate, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    domain = await ds.get_or_404(db, "state_domains", domain_id, "Terre de l'État")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aucune modification fournie.")
    await db["state_domains"].update_one({"_id": domain["_id"]}, {"$set": {**changes, "updated_at": utcnow()}})
    return serialize_doc(await db["state_domains"].find_one({"_id": domain["_id"]}))


@router.post("/domains/{domain_id}/retire", response_model=DomainOut, tags=["Domaine de l'État"],
             summary="Retirer la terre du programme (superviseur)")
async def retire_domain(domain_id: str, payload: ReasonInput, db=Depends(get_database), sup: CurrentUser = Depends(SUPERVISOR)):
    domain = await ds.get_or_404(db, "state_domains", domain_id, "Terre de l'État")
    if domain["status"] != "disponible":
        raise ds.conflict("Seule une terre disponible (sans appel ni concession en cours) peut être retirée.")
    await db["state_domains"].update_one({"_id": domain["_id"]}, {"$set": {
        "status": "retire", "retired_reason": payload.reason, "retired_by": sup.npi, "updated_at": utcnow()}})
    return serialize_doc(await db["state_domains"].find_one({"_id": domain["_id"]}))


# ================================================================================
# Appels à candidatures
# ================================================================================

@router.post("/domains/{domain_id}/calls", status_code=status.HTTP_201_CREATED, response_model=CallOut, tags=["Appels à candidatures"],
             summary="Rédiger un appel (brouillon)")
async def create_call(domain_id: str, payload: CallCreate, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    domain = await ds.get_or_404(db, "state_domains", domain_id, "Terre de l'État")
    if domain["status"] != "disponible":
        raise ds.conflict("Cette terre n'est pas disponible (appel ou concession en cours, ou terre retirée).")
    if await db["calls"].count_documents({"domain_id": domain_id, "status": {"$in": ds.OPEN_CALL_STATUSES}}):
        raise ds.conflict("Un appel est déjà en préparation ou en cours pour cette terre.")
    now = utcnow()
    doc = {**payload.model_dump(mode="json"), "opens_at": as_utc(payload.opens_at), "closes_at": as_utc(payload.closes_at),
           "domain_id": domain_id, "domain_name": domain["name"], "department": domain["department"], "commune": domain["commune"],
           "surface_hectares": domain["surface_hectares"], "status": "brouillon", "applications_count": 0, "award": None,
           "created_by": agent.npi, "history": [_history("creation", agent.npi)], "created_at": now, "updated_at": now}
    res = await db["calls"].insert_one(doc)
    doc["_id"] = res.inserted_id
    return ds.call_out(doc)


@router.post("/calls/{call_id}/publish", response_model=CallOut, tags=["Appels à candidatures"],
             summary="Publier l'appel (superviseur, autre que le rédacteur)")
async def publish_call(call_id: str, db=Depends(get_database), sup: CurrentUser = Depends(SUPERVISOR)):
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    if call["status"] != "brouillon":
        raise ds.conflict("Seul un brouillon peut être publié.")
    _four_eyes(sup, call["created_by"], "La publication d'un appel")
    domain = await ds.get_or_404(db, "state_domains", call["domain_id"], "Terre de l'État")
    if domain["dispute_flag"]:
        raise ds.conflict("La terre fait l'objet d'un litige ouvert : publication impossible.")

    now = utcnow()
    opens_at = max(as_utc(call["opens_at"]), now)  # la publicité commence au plus tôt à la publication
    if (as_utc(call["closes_at"]) - opens_at).days < settings.CALL_MIN_OPEN_DAYS:
        raise HTTPException(status_code=422, detail=f"L'appel doit rester ouvert au moins {settings.CALL_MIN_OPEN_DAYS} jours après publication.")

    await db["calls"].update_one({"_id": call["_id"]}, {
        "$set": {"status": "publie", "opens_at": opens_at, "published_by": sup.npi, "published_at": now, "updated_at": now},
        "$push": {"history": _history("publication", sup.npi)},
    })
    await db["state_domains"].update_one({"_id": domain["_id"]}, {"$set": {"status": "appel_en_cours", "current_call_id": call_id, "updated_at": now}})

    # Les exploitants éligibles sont prévenus
    eligible = []
    for npi, s in (await compute_scores(db)).items():
        if s["eligible"] and s["score"] >= call["min_score"] and (
                not call["eligible_departments"] or set(s["stats"]["departments"]) & set(call["eligible_departments"])):
            eligible.append(npi)
    await notify(db, eligible, "call_published", "Nouvelle terre de l'État à attribuer",
                 f"{call['domain_name']} ({call['surface_hectares']} ha, {call['commune']}) : candidatures ouvertes jusqu'au "
                 f"{as_utc(call['closes_at']):%d/%m/%Y}.", {"call_id": call_id})
    return ds.call_out(await db["calls"].find_one({"_id": call["_id"]}))


@router.post("/calls/{call_id}/cancel", response_model=CallOut, tags=["Appels à candidatures"], summary="Annuler l'appel (superviseur)")
async def cancel_call(call_id: str, payload: ReasonInput, db=Depends(get_database), sup: CurrentUser = Depends(SUPERVISOR)):
    return await _close_call(db, call_id, "annule", payload.reason, sup)


@router.post("/calls/{call_id}/unsuccessful", response_model=CallOut, tags=["Appels à candidatures"],
             summary="Déclarer l'appel infructueux (superviseur)")
async def unsuccessful_call(call_id: str, payload: ReasonInput, db=Depends(get_database), sup: CurrentUser = Depends(SUPERVISOR)):
    return await _close_call(db, call_id, "infructueux", payload.reason, sup)


async def _close_call(db, call_id: str, new_status: str, reason: str, sup: CurrentUser) -> dict:
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    award = call.get("award") or {}
    pending_award = call["status"] == "attribue" and not award.get("accepted_at")
    if call["status"] not in ("brouillon", "publie", "attribution_proposee") and not pending_award:
        raise ds.conflict("Cet appel ne peut plus être clôturé de cette façon (attribution déjà acceptée ou terminée).")
    now = utcnow()
    if pending_award:  # lauréat qui n'a pas confirmé : son dossier est clos
        await db["applications"].update_one({"_id": ds.parse_object_id(award["application_id"])},
                                            {"$set": {"status": "desistement" if _award_lapsed(call) else "non_retenue", "updated_at": now}})
    await db["calls"].update_one({"_id": call["_id"]}, {"$set": {"status": new_status, "updated_at": now},
                                                        "$push": {"history": _history(new_status, sup.npi, reason)}})
    await db["state_domains"].update_one({"current_call_id": call_id}, {"$set": {"status": "disponible", "current_call_id": None, "updated_at": now}})
    applicants = await db["applications"].distinct("farmer_npi", {"call_id": call_id, "status": "deposee"})
    await db["applications"].update_many({"call_id": call_id, "status": "deposee"}, {"$set": {"status": "non_retenue", "updated_at": now}})
    label = "annulé" if new_status == "annule" else "déclaré infructueux"
    await notify(db, applicants, "call_updated", "Appel à candidatures clôturé", f"L'appel « {call['title']} » a été {label} : {reason}", {"call_id": call_id})
    return ds.call_out(await db["calls"].find_one({"_id": call["_id"]}))


@router.get("/calls", response_model=list[PublicCallOut], tags=["Appels à candidatures"], summary="Appels publiés (public)")
async def list_public_calls(
    db=Depends(get_database),
    phase: Optional[str] = Query(None, description="a_venir, ouvert ou cloture"),
    department: Optional[str] = None,
):
    filters: dict = {"status": {"$in": ["publie", "attribution_proposee", "attribue", "concede", "infructueux"]}}
    if department:
        filters["department"] = department
    calls = [c async for c in db["calls"].find(filters).sort("published_at", -1)]
    domains = {str(d["_id"]): d async for d in db["state_domains"].find({"_id": {"$in": [ds.parse_object_id(c["domain_id"]) for c in calls]}})}
    out = [ds.public_call_out(c, domains[c["domain_id"]]) for c in calls if c["domain_id"] in domains]
    return [c for c in out if not phase or c["phase"] == phase]


@router.get("/calls/manage", response_model=list[CallOut], tags=["Appels à candidatures"], summary="Tous les appels, y compris brouillons (agents)")
async def list_calls_for_agents(db=Depends(get_database), _: CurrentUser = Depends(AGENT), call_status: Optional[str] = Query(None, alias="status")):
    filters = {"status": call_status} if call_status else {}
    return [ds.call_out(c) async for c in db["calls"].find(filters).sort("created_at", -1)]


@router.get("/calls/applications/me", response_model=list[ApplicationOut], tags=["Appels à candidatures"], summary="Mes candidatures")
async def my_applications(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    return [serialize_doc(a) async for a in db["applications"].find({"farmer_npi": user.npi}).sort("created_at", -1)]


@router.get("/calls/{call_id}", response_model=PublicCallOut, tags=["Appels à candidatures"])
async def get_public_call(call_id: str, db=Depends(get_database)):
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    if call["status"] in ("brouillon", "annule"):
        raise ds.not_found("Appel")
    return ds.public_call_out(call, await ds.get_or_404(db, "state_domains", call["domain_id"], "Terre de l'État"))


@router.get("/calls/{call_id}/manage", response_model=CallOut, tags=["Appels à candidatures"], summary="Dossier complet de l'appel (agents)")
async def get_call_for_agents(call_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    return ds.call_out(await ds.get_or_404(db, "calls", call_id, "Appel"))


@router.get("/calls/{call_id}/eligibility/me", response_model=EligibilityOut, tags=["Appels à candidatures"],
            summary="Puis-je candidater ? (avec les raisons)")
async def my_eligibility(call_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    reasons, score = await ds.eligibility(db, call, user.npi, user.role)
    if ds.call_phase(call) != "ouvert":
        reasons.append({"code": "phase", "message": "L'appel n'est pas ouvert aux candidatures."})
    applied = bool(await db["applications"].count_documents({"call_id": call_id, "farmer_npi": user.npi, "status": {"$ne": "retiree"}}))
    return EligibilityOut(eligible=not reasons and not applied, reasons=[r["message"] for r in reasons],
                          score=score["score"], min_score=call["min_score"], already_applied=applied)


@router.post("/calls/{call_id}/applications", status_code=status.HTTP_201_CREATED, response_model=ApplicationOut, tags=["Appels à candidatures"])
async def apply_to_call(call_id: str, payload: ApplicationCreate, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    if ds.call_phase(call) != "ouvert":
        raise ds.conflict("L'appel n'est pas ouvert aux candidatures.")
    if payload.proposed_crop.lower() not in (c.lower() for c in call["allowed_crops"]):
        raise HTTPException(status_code=422, detail=f"Cultures autorisées : {', '.join(call['allowed_crops'])}.")
    reasons, score = await ds.eligibility(db, call, user.npi, user.role)
    if reasons:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"message": "Candidature impossible.", "reasons": [r["message"] for r in reasons]})

    now = utcnow()
    existing = await db["applications"].find_one({"call_id": call_id, "farmer_npi": user.npi})
    doc = {**payload.model_dump(), "call_id": call_id, "farmer_npi": user.npi, "farmer_name": score.get("full_name"),
           "score_at_submission": score["score"], "score_components": score["components"], "status": "deposee",
           "created_at": now, "updated_at": now}
    if existing and existing["status"] != "retiree":
        raise ds.conflict("Vous avez déjà candidaté à cet appel.")
    if existing:  # nouvelle candidature après un retrait
        await db["applications"].update_one({"_id": existing["_id"]}, {"$set": doc})
        doc["_id"] = existing["_id"]
    else:
        try:
            doc["_id"] = (await db["applications"].insert_one(doc)).inserted_id
        except DuplicateKeyError:
            raise ds.conflict("Vous avez déjà candidaté à cet appel.")
    await db["calls"].update_one({"_id": call["_id"]}, {"$inc": {"applications_count": 1}})
    return serialize_doc(doc)


@router.delete("/calls/{call_id}/applications/me", response_model=ApplicationOut, tags=["Appels à candidatures"],
               summary="Retirer ma candidature (tant que l'appel est ouvert)")
async def withdraw_application(call_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    app_doc = await db["applications"].find_one({"call_id": call_id, "farmer_npi": user.npi, "status": "deposee"})
    if not app_doc:
        raise ds.not_found("Candidature")
    if ds.call_phase(call) != "ouvert":
        raise ds.conflict("L'appel est clôturé : la candidature ne peut plus être retirée.")
    await db["applications"].update_one({"_id": app_doc["_id"]}, {"$set": {"status": "retiree", "updated_at": utcnow()}})
    await db["calls"].update_one({"_id": call["_id"]}, {"$inc": {"applications_count": -1}})
    return serialize_doc(await db["applications"].find_one({"_id": app_doc["_id"]}))


@router.get("/calls/{call_id}/applications", response_model=list[ApplicationOut], tags=["Appels à candidatures"],
            summary="Candidatures classées par score (agents)")
async def list_applications(call_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    await ds.get_or_404(db, "calls", call_id, "Appel")
    apps = [a async for a in db["applications"].find({"call_id": call_id, "status": {"$ne": "retiree"}})]
    current = await compute_scores(db, [a["farmer_npi"] for a in apps]) if apps else {}
    apps.sort(key=lambda a: (-a["score_at_submission"], a["created_at"]))
    out = []
    for rank, a in enumerate(apps, 1):
        out.append({**serialize_doc(a), "rank": rank, "current_score": current.get(a["farmer_npi"], {}).get("score")})
    return out


def _award_lapsed(call: dict) -> bool:
    award = call.get("award") or {}
    return (call["status"] == "attribue" and not award.get("accepted_at")
            and award.get("acceptance_deadline") and utcnow() > as_utc(award["acceptance_deadline"]))


@router.post("/calls/{call_id}/award-proposal", response_model=CallOut, tags=["Appels à candidatures"],
             summary="Proposer un lauréat après la clôture (agent)")
async def propose_award(call_id: str, payload: AwardProposal, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    lapsed = _award_lapsed(call)
    if not (ds.call_phase(call) == "cloture" or lapsed):
        raise ds.conflict("Une proposition n'est possible qu'après la clôture des candidatures (ou si le lauréat n'a pas répondu à temps).")
    now = utcnow()
    if lapsed:
        await db["applications"].update_one({"_id": ds.parse_object_id(call["award"]["application_id"])},
                                            {"$set": {"status": "desistement", "updated_at": now}})

    app_doc = await ds.get_or_404(db, "applications", payload.application_id, "Candidature")
    if app_doc["call_id"] != call_id or app_doc["status"] != "deposee":
        raise ds.conflict("Cette candidature n'est pas (ou plus) recevable pour cet appel.")
    reasons, _ = await ds.eligibility(db, call, app_doc["farmer_npi"])
    blocking = [r["message"] for r in reasons if r["code"] in ("dispute", "cap")]  # le score retenu est celui du dépôt
    if blocking:
        raise ds.conflict("Le candidat n'est plus éligible : " + " ".join(blocking))

    better = await db["applications"].count_documents({"call_id": call_id, "status": "deposee",
                                                       "score_at_submission": {"$gt": app_doc["score_at_submission"]}})
    award = {"application_id": payload.application_id, "farmer_npi": app_doc["farmer_npi"], "farmer_name": app_doc.get("farmer_name"),
             "score": app_doc["score_at_submission"], "proposed_by": agent.npi, "proposed_at": now,
             "justification": payload.justification, "deviation_from_ranking": better > 0}
    await db["calls"].update_one({"_id": call["_id"]}, {
        "$set": {"status": "attribution_proposee", "award": award, "updated_at": now},
        "$push": {"history": _history("proposition_attribution", agent.npi, payload.justification)},
    })
    return ds.call_out(await db["calls"].find_one({"_id": call["_id"]}))


@router.post("/calls/{call_id}/award-decision", response_model=CallOut, tags=["Appels à candidatures"],
             summary="Valider ou refuser la proposition (superviseur, autre que l'auteur)")
async def decide_award(call_id: str, payload: AwardDecision, db=Depends(get_database), sup: CurrentUser = Depends(SUPERVISOR)):
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    if call["status"] != "attribution_proposee":
        raise ds.conflict("Aucune proposition d'attribution en attente.")
    award = call["award"]
    _four_eyes(sup, award["proposed_by"], "Une proposition d'attribution")
    now = utcnow()

    if not payload.approve:
        await db["calls"].update_one({"_id": call["_id"]}, {
            "$set": {"status": "publie", "award": None, "updated_at": now},
            "$push": {"history": {**_history("proposition_refusee", sup.npi, payload.note), "award": award}},
        })
        return ds.call_out(await db["calls"].find_one({"_id": call["_id"]}))

    award.update({"approved_by": sup.npi, "approved_at": now, "contest_until": ds.plus_days(settings.CALL_CONTEST_DAYS),
                  "acceptance_deadline": ds.plus_days(settings.AWARD_ACCEPTANCE_DAYS)})
    await db["calls"].update_one({"_id": call["_id"]}, {
        "$set": {"status": "attribue", "award": award, "updated_at": now},
        "$push": {"history": _history("attribution_validee", sup.npi, payload.note)},
    })
    await db["applications"].update_one({"_id": ds.parse_object_id(award["application_id"])}, {"$set": {"status": "retenue", "updated_at": now}})
    await notify(db, [award["farmer_npi"]], "call_awarded", "Vous êtes retenu(e) !",
                 f"Votre candidature pour « {call['domain_name']} » est retenue. Confirmez avant le {award['acceptance_deadline']:%d/%m/%Y}.",
                 {"call_id": call_id})
    others = await db["applications"].distinct("farmer_npi", {"call_id": call_id, "status": "deposee"})
    await notify(db, others, "call_updated", "Résultat de l'appel à candidatures",
                 f"Un lauréat a été retenu pour « {call['domain_name']} ». Vous pouvez contester jusqu'au {award['contest_until']:%d/%m/%Y}.",
                 {"call_id": call_id})
    return ds.call_out(await db["calls"].find_one({"_id": call["_id"]}))


@router.post("/calls/{call_id}/acceptance", tags=["Appels à candidatures"], summary="Le lauréat accepte ou se désiste")
async def accept_award(call_id: str, payload: AcceptanceInput, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    award = call.get("award") or {}
    if call["status"] != "attribue" or award.get("farmer_npi") != user.npi:
        raise ds.not_found("Attribution")
    if award.get("accepted_at"):
        raise ds.conflict("Vous avez déjà accepté cette attribution.")
    if utcnow() > as_utc(award["acceptance_deadline"]):
        raise ds.conflict("Le délai d'acceptation est dépassé.")
    now = utcnow()

    if not payload.accept:
        await db["applications"].update_one({"_id": ds.parse_object_id(award["application_id"])}, {"$set": {"status": "desistement", "updated_at": now}})
        await db["calls"].update_one({"_id": call["_id"]}, {
            "$set": {"status": "publie", "award": None, "updated_at": now},
            "$push": {"history": {**_history("desistement", user.npi, payload.note), "award": award}},
        })
        return {"status": "desistement", "call_id": call_id}

    app_doc = await ds.get_or_404(db, "applications", award["application_id"], "Candidature")
    concession = {
        "call_id": call_id, "domain_id": call["domain_id"], "domain_name": call["domain_name"], "department": call["department"],
        "commune": call["commune"], "surface_hectares": call["surface_hectares"], "farmer_npi": user.npi, "farmer_name": award.get("farmer_name"),
        "contract_type": call["contract_type"], "duration_years": call["duration_years"], "crop_type": app_doc["proposed_crop"],
        "planned_yield_kg": app_doc["planned_yield_kg"], "annual_fee_fcfa": round(call["annual_fee_fcfa_per_ha"] * call["surface_hectares"]),
        "mise_en_valeur_months": call["mise_en_valeur_months"], "cahier_des_charges": call["cahier_des_charges"],
        "status": "en_attente_acte", "payments": [], "latest_mise_en_valeur_pct": None, "history": [_history("acceptation", user.npi, payload.note)],
        "created_at": now, "updated_at": now,
    }
    res = await db["concessions"].insert_one(concession)
    award["accepted_at"] = now
    await db["calls"].update_one({"_id": call["_id"]}, {"$set": {"award": award, "concession_id": str(res.inserted_id), "updated_at": now},
                                                        "$push": {"history": _history("acceptation", user.npi)}})
    return {"status": "accepte", "call_id": call_id, "concession_id": str(res.inserted_id),
            "message": "Acceptation enregistrée. La concession sera active après signature de l'acte officiel."}


@router.post("/calls/{call_id}/contestations", status_code=status.HTTP_201_CREATED, response_model=ContestationOut, tags=["Appels à candidatures"],
             summary="Contester l'attribution (candidats, pendant le délai)")
async def contest_award(call_id: str, payload: ContestationCreate, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    award = call.get("award") or {}
    if call["status"] != "attribue" or not award.get("contest_until") or utcnow() > as_utc(award["contest_until"]):
        raise ds.conflict("Aucune attribution contestable pour cet appel (ou délai de contestation dépassé).")
    if user.npi == award["farmer_npi"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Le lauréat ne peut pas contester sa propre attribution.")
    if not await db["applications"].count_documents({"call_id": call_id, "farmer_npi": user.npi, "status": {"$ne": "retiree"}}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seuls les candidats peuvent contester l'attribution.")
    now = utcnow()
    doc = {**payload.model_dump(), "call_id": call_id, "npi": user.npi, "status": "ouverte", "created_at": now, "updated_at": now}
    try:
        doc["_id"] = (await db["contestations"].insert_one(doc)).inserted_id
    except DuplicateKeyError:
        raise ds.conflict("Vous avez déjà contesté cette attribution.")
    supervisors = await db["users"].distinct("npi", {"role": "state_supervisor"})
    await notify(db, supervisors, "contestation_filed", "Contestation d'une attribution",
                 f"Une contestation a été déposée pour « {call['domain_name']} ».", {"call_id": call_id})
    return serialize_doc(doc)


@router.get("/calls/{call_id}/contestations", response_model=list[ContestationOut], tags=["Appels à candidatures"])
async def list_contestations(call_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    return [serialize_doc(c) async for c in db["contestations"].find({"call_id": call_id}).sort("created_at", 1)]


@router.patch("/contestations/{contestation_id}", response_model=ContestationOut, tags=["Appels à candidatures"],
              summary="Trancher une contestation (superviseur)")
async def decide_contestation(contestation_id: str, payload: ContestationDecision, db=Depends(get_database), sup: CurrentUser = Depends(SUPERVISOR)):
    c = await ds.get_or_404(db, "contestations", contestation_id, "Contestation")
    if c["status"] != "ouverte":
        raise ds.conflict("Contestation déjà tranchée.")
    call = await ds.get_or_404(db, "calls", c["call_id"], "Appel")
    now = utcnow()
    await db["contestations"].update_one({"_id": c["_id"]}, {"$set": {
        "status": payload.decision, "decision_note": payload.note, "decided_by": sup.npi, "updated_at": now}})

    if payload.decision == "fondee" and call["status"] == "attribue":
        # L'attribution est annulée : retour à l'étape de proposition
        award = call["award"]
        await db["applications"].update_one({"_id": ds.parse_object_id(award["application_id"])}, {"$set": {"status": "non_retenue", "updated_at": now}})
        await db["concessions"].update_many({"call_id": c["call_id"], "status": "en_attente_acte"}, {"$set": {"status": "annulee", "updated_at": now}})
        await db["calls"].update_one({"_id": call["_id"]}, {
            "$set": {"status": "publie", "award": None, "concession_id": None, "updated_at": now},
            "$push": {"history": {**_history("attribution_annulee_sur_contestation", sup.npi, payload.note), "award": award}},
        })
        await notify(db, [award["farmer_npi"]], "call_updated", "Attribution annulée",
                     f"Suite à une contestation, votre attribution pour « {call['domain_name']} » est annulée : {payload.note}", {"call_id": c["call_id"]})
    await notify(db, [c["npi"]], "call_updated", "Décision sur votre contestation",
                 f"Votre contestation est jugée {'fondée' if payload.decision == 'fondee' else 'non fondée'} : {payload.note}", {"call_id": c["call_id"]})
    return serialize_doc(await db["contestations"].find_one({"_id": c["_id"]}))


# ================================================================================
# Concessions
# ================================================================================

@router.get("/concessions", tags=["Concessions"], summary="Concessions (agents)")
async def list_concessions(db=Depends(get_database), _: CurrentUser = Depends(AGENT), concession_status: Optional[str] = Query(None, alias="status")):
    filters = {"status": concession_status} if concession_status else {}
    return [ds.concession_out(c) async for c in db["concessions"].find(filters).sort("created_at", -1)]


@router.get("/concessions/me", tags=["Concessions"], summary="Mes concessions")
async def my_concessions(db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    return [ds.concession_out(c) async for c in db["concessions"].find({"farmer_npi": user.npi}).sort("created_at", -1)]


async def _concession_for(db, concession_id: str, user: CurrentUser) -> dict:
    c = await ds.get_or_404(db, "concessions", concession_id, "Concession")
    if c["farmer_npi"] != user.npi and not user.is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")
    return c


@router.get("/concessions/{concession_id}", tags=["Concessions"])
async def get_concession(concession_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    c = await _concession_for(db, concession_id, user)
    out = ds.concession_out(c)
    out["reports"] = [serialize_doc(r) async for r in db["concession_reports"].find({"concession_id": concession_id}).sort("season", -1)]
    out["inspections"] = [serialize_doc(i) async for i in db["concession_inspections"].find({"concession_id": concession_id}).sort("created_at", -1)]
    return out


@router.post("/concessions/{concession_id}/official-act", tags=["Concessions"],
             summary="Enregistrer l'acte officiel : la concession devient active (agent)")
async def record_official_act(concession_id: str, payload: OfficialActInput, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    c = await ds.get_or_404(db, "concessions", concession_id, "Concession")
    if c["status"] != "en_attente_acte":
        raise ds.conflict("Cette concession n'attend pas d'acte.")
    call = await ds.get_or_404(db, "calls", c["call_id"], "Appel")
    award = call["award"]
    if utcnow() <= as_utc(award["contest_until"]):
        raise ds.conflict(f"Le délai de contestation court jusqu'au {as_utc(award['contest_until']):%d/%m/%Y}.")
    if await db["contestations"].count_documents({"call_id": c["call_id"], "status": "ouverte"}):
        raise ds.conflict("Une contestation est encore ouverte.")

    start = datetime.combine(payload.act_date, time.min, tzinfo=timezone.utc)
    now = utcnow()
    await db["concessions"].update_one({"_id": c["_id"]}, {
        "$set": {"status": "active", "act_ref": payload.act_ref, "act_date": start, "authority": payload.authority,
                 "start_date": start, "end_date": ds.add_years(start, c["duration_years"]),
                 "mise_en_valeur_deadline": start + timedelta(days=round(c["mise_en_valeur_months"] * 30.44)),
                 "updated_at": now},
        "$push": {"history": _history("acte_enregistre", agent.npi, payload.act_ref)},
    })
    await db["calls"].update_one({"_id": call["_id"]}, {"$set": {"status": "concede", "updated_at": now},
                                                        "$push": {"history": _history("concession_active", agent.npi, payload.act_ref)}})
    await db["state_domains"].update_one({"_id": ds.parse_object_id(c["domain_id"])}, {"$set": {
        "status": "attribue", "current_call_id": None, "current_concession_id": concession_id, "updated_at": now}})
    others = await db["applications"].distinct("farmer_npi", {"call_id": c["call_id"], "status": "deposee"})
    await db["applications"].update_many({"call_id": c["call_id"], "status": "deposee"}, {"$set": {"status": "non_retenue", "updated_at": now}})
    await notify(db, [c["farmer_npi"]], "concession_active", "Concession active",
                 f"L'acte {payload.act_ref} est enregistré : vous pouvez exploiter « {c['domain_name']} ».", {"concession_id": concession_id})
    await notify(db, others, "call_updated", "Appel à candidatures clôturé", f"La terre « {c['domain_name']} » a été attribuée.", {"call_id": c["call_id"]})
    return ds.concession_out(await db["concessions"].find_one({"_id": c["_id"]}))


def _require_active(c: dict) -> None:
    if c["status"] != "active":
        raise ds.conflict("La concession n'est pas active.")


@router.post("/concessions/{concession_id}/reports", status_code=status.HTTP_201_CREATED, tags=["Concessions"],
             summary="Déclarer une récolte sur la terre de l'État (titulaire)")
async def add_report(concession_id: str, payload: ConcessionReportCreate, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    c = await ds.get_or_404(db, "concessions", concession_id, "Concession")
    if c["farmer_npi"] != user.npi:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seul le titulaire déclare les récoltes.")
    _require_active(c)
    if payload.area_cultivated_ha > c["surface_hectares"] * 1.01:
        raise HTTPException(status_code=422, detail="La surface cultivée dépasse la surface de la concession.")
    doc = {**payload.model_dump(), "concession_id": concession_id, "farmer_npi": user.npi, "department": c["department"],
           "commune": c["commune"], "expected_yield_kg": round(c["planned_yield_kg"] * payload.area_cultivated_ha / c["surface_hectares"]),
           "created_at": utcnow()}
    try:
        doc["_id"] = (await db["concession_reports"].insert_one(doc)).inserted_id
    except DuplicateKeyError:
        raise ds.conflict("Une récolte est déjà déclarée pour cette saison et cette culture.")
    return serialize_doc(doc)


@router.post("/concessions/{concession_id}/inspections", status_code=status.HTTP_201_CREATED, tags=["Concessions"],
             summary="Enregistrer une inspection de mise en valeur (agent)")
async def add_inspection(concession_id: str, payload: InspectionCreate, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    c = await ds.get_or_404(db, "concessions", concession_id, "Concession")
    _require_active(c)
    now = utcnow()
    doc = {**payload.model_dump(mode="json"), "concession_id": concession_id, "inspector_npi": agent.npi, "created_at": now}
    doc["_id"] = (await db["concession_inspections"].insert_one(doc)).inserted_id
    await db["concessions"].update_one({"_id": c["_id"]}, {"$set": {
        "latest_mise_en_valeur_pct": payload.mise_en_valeur_pct, "latest_compliant": payload.compliant, "last_inspection_at": now, "updated_at": now}})
    await notify(db, [c["farmer_npi"]], "concession_inspection", "Inspection de votre concession",
                 f"Mise en valeur constatée : {payload.mise_en_valeur_pct:.0f} %. {payload.note}", {"concession_id": concession_id})
    return serialize_doc(doc)


@router.post("/concessions/{concession_id}/payments", tags=["Concessions"], summary="Enregistrer un paiement de redevance (agent)")
async def add_payment(concession_id: str, payload: PaymentCreate, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    c = await ds.get_or_404(db, "concessions", concession_id, "Concession")
    if c["status"] not in ("active", "terminee", "retiree"):
        raise ds.conflict("Aucune redevance n'est due avant l'acte officiel.")
    if any(p["receipt_ref"] == payload.receipt_ref for p in c.get("payments", [])):
        raise ds.conflict("Ce reçu est déjà enregistré.")
    await db["concessions"].update_one({"_id": c["_id"]}, {"$push": {"payments": {
        **payload.model_dump(), "recorded_by": agent.npi, "recorded_at": utcnow()}}, "$set": {"updated_at": utcnow()}})
    return ds.concession_out(await db["concessions"].find_one({"_id": c["_id"]}))


@router.post("/concessions/{concession_id}/termination", tags=["Concessions"], summary="Retirer ou clore la concession (superviseur)")
async def terminate_concession(concession_id: str, payload: TerminationInput, db=Depends(get_database), sup: CurrentUser = Depends(SUPERVISOR)):
    c = await ds.get_or_404(db, "concessions", concession_id, "Concession")
    _require_active(c)
    now = utcnow()
    await db["concessions"].update_one({"_id": c["_id"]}, {
        "$set": {"status": payload.status, "termination_reason": payload.reason, "termination_note": payload.note, "ended_at": now, "updated_at": now},
        "$push": {"history": _history(payload.status, sup.npi, f"{payload.reason} : {payload.note}")},
    })
    await db["state_domains"].update_one({"_id": ds.parse_object_id(c["domain_id"])}, {"$set": {
        "status": "disponible", "current_concession_id": None, "updated_at": now}})
    label = "retirée" if payload.status == "retiree" else "terminée"
    await notify(db, [c["farmer_npi"]], "concession_ended", "Fin de concession",
                 f"Votre concession « {c['domain_name']} » est {label} : {payload.note}", {"concession_id": concession_id})
    return ds.concession_out(await db["concessions"].find_one({"_id": c["_id"]}))
