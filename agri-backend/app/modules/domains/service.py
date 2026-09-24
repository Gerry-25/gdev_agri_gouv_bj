import math
from datetime import timedelta

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.utils import as_utc, parse_object_id, serialize_doc, utcnow
from app.modules.performance.service import compute_score

OPEN_CALL_STATUSES = ["brouillon", "publie", "attribution_proposee", "attribue"]


def not_found(label: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} introuvable.")


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def get_or_404(db, collection: str, oid: str, label: str) -> dict:
    doc = await db[collection].find_one({"_id": parse_object_id(oid, label)})
    if not doc:
        raise not_found(label)
    return doc


def call_phase(call: dict):
    if call["status"] != "publie":
        return None
    now = utcnow()
    if now < as_utc(call["opens_at"]):
        return "a_venir"
    return "ouvert" if now <= as_utc(call["closes_at"]) else "cloture"


def call_out(call: dict) -> dict:
    out = serialize_doc(call)
    out["phase"] = call_phase(call)
    return out


def public_call_out(call: dict, domain: dict) -> dict:
    award = call.get("award") or {}
    shown = call["status"] in ("attribue", "concede") and award.get("approved_at")
    return {
        **{k: call[k] for k in ("title", "description", "cahier_des_charges", "allowed_crops", "contract_type", "duration_years",
                                "annual_fee_fcfa_per_ha", "mise_en_valeur_months", "min_score", "eligible_departments",
                                "opens_at", "closes_at", "status", "domain_name", "department", "commune",
                                "surface_hectares", "applications_count")},
        "id": str(call["_id"]),
        "phase": call_phase(call),
        "boundary": domain["boundary"],
        "awarded_to_name": award.get("farmer_name") if shown else None,
        "contest_until": award.get("contest_until") if shown else None,
    }


async def eligibility(db, call: dict, npi: str, role: str = "farmer") -> tuple[list[dict], dict]:
    """Motifs d'inéligibilité (avec un code) et score actuel de l'exploitant."""
    reasons = []
    if role != "farmer":
        reasons.append({"code": "role", "message": "Seuls les exploitants peuvent candidater."})
    score = await compute_score(db, npi)
    for r in score["ineligibility_reasons"]:
        reasons.append({"code": "dispute" if "litige" in r else "seasons", "message": r})
    if score["score"] < call["min_score"]:
        reasons.append({"code": "score", "message": f"Score de {score['score']} inférieur au minimum requis ({call['min_score']})."})
    if call.get("eligible_departments"):
        if not set(score["stats"]["departments"]) & set(call["eligible_departments"]):
            reasons.append({"code": "department", "message": f"Réservé aux exploitants ayant une parcelle dans : {', '.join(call['eligible_departments'])}."})
    active = await db["concessions"].count_documents({"farmer_npi": npi, "status": {"$in": ["en_attente_acte", "active"]}})
    if active >= settings.MAX_ACTIVE_CONCESSIONS_PER_FARMER:
        reasons.append({"code": "cap", "message": "Nombre maximal de concessions en cours atteint."})
    return reasons, score


def concession_out(doc: dict) -> dict:
    out = serialize_doc(doc)
    paid = sum(p["amount_fcfa"] for p in doc.get("payments", []))
    due = 0.0
    alert = False
    if doc.get("start_date"):
        start = as_utc(doc["start_date"])
        years = max(1, math.ceil((min(utcnow(), as_utc(doc["end_date"])) - start).days / 365.25))
        due = doc["annual_fee_fcfa"] * years
        deadline = as_utc(doc["mise_en_valeur_deadline"])
        alert = doc["status"] == "active" and utcnow() > deadline and (doc.get("latest_mise_en_valeur_pct") or 0) < 50
    out.update({"fees_due_fcfa": round(due), "fees_paid_fcfa": round(paid), "balance_fcfa": round(due - paid), "mise_en_valeur_alert": alert})
    return out


def add_years(d, years: int):
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 février
        return d.replace(year=d.year + years, day=28)


def plus_days(days: int):
    return utcnow() + timedelta(days=days)
