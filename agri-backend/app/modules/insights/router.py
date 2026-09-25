"""Aide à la décision pour les agents : synthèses de litiges, priorités d'inspection, note hebdomadaire,
analyse des concessions. Les priorités sont calculées par des règles transparentes ; l'IA rédige."""
from collections import defaultdict
from datetime import timedelta
from statistics import median
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core import ai_service
from app.core.database import get_database
from app.core.security import CurrentUser, require_roles
from app.core.utils import as_utc, parse_object_id, serialize_doc, utcnow
from app.modules.domains import service as ds
from app.modules.state import router as state

router = APIRouter(tags=["Aide à la décision (agents)"])
AGENT = require_roles("state_agent")


# --- Synthèse d'un litige --------------------------------------------------------------

class DisputeSummary(BaseModel):
    neutral_summary: str
    chronology: list[str]
    established_facts: list[str]
    points_of_contention: list[str]
    missing_information: list[str]
    mediation_questions: list[str]
    suggested_next_steps: list[str]


@router.post("/lands/disputes/{dispute_id}/ai-summary", summary="Synthèse neutre d'un litige pour la médiation (IA)")
async def dispute_summary(dispute_id: str, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    d = await ds.get_or_404(db, "disputes", dispute_id, "Litige")
    # Les parties sont anonymisées : « partie A », « partie B »…
    alias = {npi: f"partie {chr(65 + i)}" for i, npi in enumerate(d["parties_npi"])}
    lands = []
    for lid in d["land_ids"]:
        land = await db["lands"].find_one({"_id": parse_object_id(lid)})
        if land:
            lands.append({"proprietaire": alias.get(land["npi_owner"], "tiers"), "surface_ha": land["surface_hectares"],
                          "culture": land["crop_type"], "verification": land.get("verification_status"),
                          "enregistree_le": land["created_at"], "contours_modifies": len(land.get("boundary_history", [])),
                          "transferts": len(land.get("ownership_history", []))})
    history = [{"statut": h.get("status"), "auteur": alias.get(h.get("by"), "agent" if h.get("by") not in ("systeme", None) else "systeme"),
                "note": h.get("note"), "date": h.get("at")} for h in d.get("history", [])]
    context = {"type": d["type"], "statut": d["status"], "motif": d["reason"], "surface_en_chevauchement_m2": d.get("overlap_area_m2"),
               "commune": d.get("commune"), "terre_de_l_etat_concernee": bool(d.get("domain_id")),
               "signale_par": alias.get(d["reported_by"], d["reported_by"]), "parcelles": lands, "historique": history}
    prompt = ("Prépare une synthèse strictement neutre d'un litige foncier pour un agent médiateur. Ne prends pas parti, "
              "ne désigne pas de responsable, distingue les faits établis des affirmations, et liste les pièces à demander.\n"
              + ai_service.to_prompt_json(context))
    out, run_id = await ai_service.generate(db, purpose="dispute_summary", schema=DisputeSummary, prompt=prompt, requested_by=agent.npi, temperature=0.2)
    res = {**out.model_dump(), "parties": {v: "voir le dossier" for v in alias.values()}, **ai_service.ai_meta(run_id)}
    await db["disputes"].update_one({"_id": d["_id"]}, {"$set": {"ai_summary": res}})
    return res


# --- Priorités d'inspection (règles transparentes, sans IA) ------------------------------

async def _priorities(db, department: Optional[str], limit: int) -> list[dict]:
    items = []
    now = utcnow()
    base = {"department": department} if department else {}

    async for land in db["lands"].find({**base, "verification_status": {"$in": ["declaree", None]}}).sort("created_at", 1).limit(limit):
        age = (now - as_utc(land["created_at"])).days
        items.append({"kind": "verification", "target_id": str(land["_id"]), "commune": land["commune"], "department": land["department"],
                      # Plafonnée à 65 (85 en litige) : une ancienne déclaration ne doit pas masquer un foyer sanitaire
                      "priority": min(65, 20 + age // 10) + (20 if land.get("dispute_flag") else 0),
                      "reason": f"Parcelle déclarée il y a {age} jours, non vérifiée" + (", en litige" if land.get("dispute_flag") else "")})

    # Rendements anormaux par rapport à la médiane (même culture, même département)
    lands = {str(l["_id"]): l async for l in db["lands"].find(base, {"surface_hectares": 1, "department": 1, "commune": 1, "verification_status": 1})}
    per = defaultdict(list)
    harvests = [h async for h in db["harvests"].find({"land_id": {"$in": list(lands)}})]
    for h in harvests:
        l = lands[h["land_id"]]
        if l["surface_hectares"]:
            per[(h["crop_type"], l["department"])].append(h["actual_yield_kg"] / l["surface_hectares"])
    for h in harvests:
        l = lands[h["land_id"]]
        values = per[(h["crop_type"], l["department"])]
        if len(values) < 5 or not l["surface_hectares"]:
            continue
        ratio = h["actual_yield_kg"] / l["surface_hectares"] / median(values)
        if ratio > 2.5 or ratio < 0.25:
            items.append({"kind": "rendement_anormal", "target_id": h["land_id"], "commune": l["commune"], "department": l["department"],
                          "priority": 70 if ratio > 2.5 else 55,
                          "reason": f"{h['crop_type']} {h['season']} : rendement {ratio:.1f} fois la médiane locale"
                                    + (" (possible surdéclaration)" if ratio > 2.5 else " (possible difficulté ou erreur de saisie)")})

    async for c in db["concessions"].find({**base, "status": "active"}):
        out = ds.concession_out(c)
        reasons = []
        if out["mise_en_valeur_alert"]:
            reasons.append("délai de mise en valeur dépassé avec moins de 50 % constatés")
        if out["balance_fcfa"] > 0:
            reasons.append(f"redevance impayée : {out['balance_fcfa']:,.0f} FCFA".replace(",", " "))
        last = c.get("last_inspection_at")
        if not last or (now - as_utc(last)).days > 180:
            reasons.append("aucune inspection depuis plus de 6 mois")
        if reasons:
            items.append({"kind": "concession", "target_id": str(c["_id"]), "commune": c["commune"], "department": c["department"],
                          "priority": 60 + 15 * len(reasons), "reason": " ; ".join(reasons)})

    hot = await state.sanitary_hotspots(db=db, days=30, min_cases=None, department=department)
    for z in hot["zones"]:
        if z["is_hotspot"]:
            items.append({"kind": "foyer_sanitaire", "target_id": None, "commune": z["commune"], "department": z["department"],
                          "priority": 90 if z["alert_level"] == "red" else 75,
                          "reason": f"{z['cases']} cas de {z['disease']} en 30 jours ({z['critical_cases']} critiques)"})
    items.sort(key=lambda i: -i["priority"])
    return items[:limit]


@router.get("/state/inspection-priorities", summary="Où aller en priorité (règles transparentes)")
async def inspection_priorities(db=Depends(get_database), _: CurrentUser = Depends(AGENT),
                                department: Optional[str] = None, limit: int = Query(30, ge=1, le=200)):
    return await _priorities(db, department, limit)


# --- Note hebdomadaire ---------------------------------------------------------------------

class PriorityAction(BaseModel):
    action: str
    zone: str
    reason: str


class WeeklyReport(BaseModel):
    title: str
    highlights: list[str]
    sanitary_situation: str
    land_situation: str
    market_situation: str
    priority_actions: list[PriorityAction]
    watch_points: list[str]


@router.post("/state/reports/weekly", status_code=201, summary="Note de synthèse de la semaine (IA)")
async def weekly_report(db=Depends(get_database), agent: CurrentUser = Depends(AGENT), department: Optional[str] = None):
    week = utcnow() - timedelta(days=7)
    base = {"department": department} if department else {}
    context = {
        "perimetre": department or "national",
        "indicateurs": await state.get_state_metrics(db=db, days=7),
        "nouveautes_7_jours": {
            "parcelles": await db["lands"].count_documents({**base, "created_at": {"$gte": week}}),
            "diagnostics": await db["phytosanitary_alerts"].count_documents({**base, "observed_at": {"$gte": week}}),
            "litiges": await db["disputes"].count_documents({**base, "created_at": {"$gte": week}}),
            "offres": await db["market_offers"].count_documents({**base, "created_at": {"$gte": week}}),
        },
        "zones": (await state.stats_by_zone(db=db, level="commune" if department else "department", department=department, days=30))[:15],
        "foyers_sanitaires": (await state.sanitary_hotspots(db=db, days=30, min_cases=None, department=department))["zones"][:10],
        "priorites_calculees": await _priorities(db, department, 15),
    }
    prompt = ("Rédige la note hebdomadaire d'un service agricole de l'État. Factuelle, chiffrée, sans extrapolation : "
              "n'utilise que les données fournies. Termine par des actions prioritaires localisées.\n" + ai_service.to_prompt_json(context))
    out, run_id = await ai_service.generate(db, purpose="weekly_report", schema=WeeklyReport, prompt=prompt, requested_by=agent.npi)
    doc = {"scope": department or "national", "report": out.model_dump(), **ai_service.ai_meta(run_id), "created_by": agent.npi, "created_at": utcnow()}
    doc["_id"] = (await db["reports"].insert_one(doc)).inserted_id
    return serialize_doc({k: v for k, v in doc.items() if k != "created_by"})


@router.get("/state/reports", summary="Notes précédentes")
async def list_reports(db=Depends(get_database), _: CurrentUser = Depends(AGENT), limit: int = Query(20, ge=1, le=100)):
    return [serialize_doc(r) async for r in db["reports"].find({}, {"created_by": 0}).sort("created_at", -1).limit(limit)]


# --- Analyse d'une concession --------------------------------------------------------------

class ConcessionReview(BaseModel):
    assessment: Literal["conforme", "a_surveiller", "risque_de_defaut"]
    findings: list[str]
    early_warnings: list[str]
    recommended_actions: list[str]
    next_inspection_focus: list[str]


@router.post("/concessions/{concession_id}/ai-review", summary="Analyse du suivi d'une concession (IA)")
async def concession_review(concession_id: str, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    c = await ds.get_or_404(db, "concessions", concession_id, "Concession")
    out = ds.concession_out(c)
    call = await db["calls"].find_one({"_id": parse_object_id(c["call_id"])})
    plan = await db["domain_plans"].find_one({"_id": parse_object_id(call["plan_id"])}) if call and call.get("plan_id") else None
    context = {
        "concession": {k: out.get(k) for k in ("status", "surface_hectares", "crop_type", "planned_yield_kg", "duration_years", "start_date",
                                               "end_date", "mise_en_valeur_deadline", "latest_mise_en_valeur_pct", "latest_compliant",
                                               "fees_due_fcfa", "fees_paid_fcfa", "balance_fcfa", "mise_en_valeur_alert")},
        "cahier_des_charges": c.get("cahier_des_charges"),
        "indicateurs_du_plan": (plan or {}).get("plan", {}).get("valorization_indicators"),
        "rapports_de_campagne": [{k: r[k] for k in ("season", "crop_type", "area_cultivated_ha", "actual_yield_kg", "expected_yield_kg")}
                                 async for r in db["concession_reports"].find({"concession_id": concession_id})],
        "inspections": [{k: i.get(k) for k in ("mise_en_valeur_pct", "compliant", "note", "created_at")}
                        async for i in db["concession_inspections"].find({"concession_id": concession_id}).sort("created_at", 1)],
        "aujourd_hui": utcnow(),
    }
    prompt = ("Analyse le suivi de cette concession agricole au regard du cahier des charges. Signale tôt les risques de défaut "
              "de mise en valeur ou de paiement. Tu n'es pas décideur : propose des actions et les points à vérifier.\n"
              + ai_service.to_prompt_json(context))
    review, run_id = await ai_service.generate(db, purpose="concession_review", schema=ConcessionReview, prompt=prompt, requested_by=agent.npi)
    res = {**review.model_dump(), **ai_service.ai_meta(run_id)}
    await db["concessions"].update_one({"_id": c["_id"]}, {"$set": {"ai_review": res}})
    return res
