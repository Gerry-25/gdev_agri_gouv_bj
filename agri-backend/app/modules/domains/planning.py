"""Préparation des terres de l'État : relevé de terrain, orientations, photos, profil environnemental,
plan de mise en valeur par l'IA et aide à l'analyse des candidatures."""
import io
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.core import ai_service, geo
from app.core.config import settings
from app.core.database import get_database
from app.core.environment import profile as env_profile
from app.core.security import CurrentUser, require_roles
from app.core.utils import as_utc, parse_object_id, serialize_doc, utcnow
from app.modules.domains import service as ds
from app.modules.domains.planning_schemas import ApplicationReview, PlanOut, PlanReview, SiteSurvey, StateOrientation, ValorizationPlan

router = APIRouter(tags=["Domaine de l'État : préparation et plan IA"])
AGENT = require_roles("state_agent")

MAX_PHOTOS = 12
PHOTOS_TO_AI = 4


async def _domain(db, domain_id: str) -> dict:
    return await ds.get_or_404(db, "state_domains", domain_id, "Terre de l'État")


# --- Relevé, orientations, photos -------------------------------------------------

@router.put("/domains/{domain_id}/survey", summary="Relevé de terrain de l'agent")
async def save_survey(domain_id: str, payload: SiteSurvey, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    d = await _domain(db, domain_id)
    await db["state_domains"].update_one({"_id": d["_id"]}, {"$set": {
        "survey": {**payload.model_dump(mode="json"), "surveyed_by": agent.npi, "saved_at": utcnow()}, "updated_at": utcnow()}})
    return {"status": "enregistre", "readiness": await _readiness(db, await _domain(db, domain_id))}


@router.put("/domains/{domain_id}/orientation", summary="Orientations de l'État pour cette terre")
async def save_orientation(domain_id: str, payload: StateOrientation, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    d = await _domain(db, domain_id)
    await db["state_domains"].update_one({"_id": d["_id"]}, {"$set": {
        "orientation": {**payload.model_dump(mode="json"), "set_by": agent.npi, "saved_at": utcnow()}, "updated_at": utcnow()}})
    return {"status": "enregistre", "readiness": await _readiness(db, await _domain(db, domain_id))}


@router.post("/domains/{domain_id}/photos", status_code=status.HTTP_201_CREATED, summary="Ajouter une photo géolocalisée")
async def add_photo(
    domain_id: str,
    file: UploadFile = File(...),
    caption: str = Form("", max_length=200),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    db=Depends(get_database),
    agent: CurrentUser = Depends(AGENT),
):
    d = await _domain(db, domain_id)
    if await db["domain_photos"].count_documents({"domain_id": domain_id}) >= MAX_PHOTOS:
        raise ds.conflict(f"{MAX_PHOTOS} photos maximum par terre.")
    raw = await file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"Photo trop volumineuse ({settings.MAX_UPLOAD_SIZE_MB} Mo maximum).")
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Image illisible.")
    img.thumbnail((1280, 1280))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=72, optimize=True)
    doc = {"domain_id": domain_id, "data": buf.getvalue(), "caption": caption, "taken_by": agent.npi, "created_at": utcnow()}
    if latitude is not None and longitude is not None:
        doc["location"] = {"type": "Point", "coordinates": [longitude, latitude]}
    res = await db["domain_photos"].insert_one(doc)
    await db["state_domains"].update_one({"_id": d["_id"]}, {"$inc": {"photos_count": 1}})
    return {"id": str(res.inserted_id), "url": f"{settings.API_V1_STR}/domains/{domain_id}/photos/{res.inserted_id}"}


@router.get("/domains/{domain_id}/photos")
async def list_photos(domain_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    return [{"id": str(p["_id"]), "caption": p.get("caption"), "location": p.get("location"), "created_at": p["created_at"],
             "url": f"{settings.API_V1_STR}/domains/{domain_id}/photos/{p['_id']}"}
            async for p in db["domain_photos"].find({"domain_id": domain_id}, {"data": 0}).sort("created_at", 1)]


@router.get("/domains/{domain_id}/photos/{photo_id}", response_class=Response, responses={200: {"content": {"image/jpeg": {}}}})
async def get_photo(domain_id: str, photo_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    p = await db["domain_photos"].find_one({"_id": parse_object_id(photo_id, "Photo"), "domain_id": domain_id})
    if not p:
        raise ds.not_found("Photo")
    return Response(content=bytes(p["data"]), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=2592000"})


# --- Profil environnemental ----------------------------------------------------------

async def _refresh_environment(db, d: dict) -> dict:
    poly = geo.from_geojson(d["boundary"])
    zone = (d.get("survey") or {}).get("agroecological_zone")
    env = await env_profile.collect(poly, d["department"], d["commune"], zone, full=True)
    await db["state_domains"].update_one({"_id": d["_id"]}, {"$set": {"environment": env, "updated_at": utcnow()}})
    return env


@router.post("/domains/{domain_id}/environment", summary="Collecter sol, climat, relief et accessibilité")
async def refresh_environment(domain_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    env = await _refresh_environment(db, await _domain(db, domain_id))
    return {"environment": env, "availability": env_profile.availability(env)}


async def _readiness(db, d: dict) -> dict:
    """Liste de contrôle : ce qui manque pour un plan fiable."""
    env = d.get("environment")
    avail = env_profile.availability(env)
    survey = d.get("survey") or {}
    soil_uncertain = any(r.get("uncertainty") == "forte" for r in (env or {}).get("soil_reading", []))
    checks = [
        {"item": "Profil environnemental collecté", "ok": bool(env), "required": True},
        {"item": "Données de sol disponibles", "ok": avail["soil"] == "ok" or bool(survey.get("lab_soil_analysis")), "required": False},
        {"item": "Relevé de terrain", "ok": bool(survey), "required": True},
        {"item": "Zone agroécologique confirmée", "ok": bool(survey.get("agroecological_zone")), "required": False},
        {"item": "Orientations de l'État", "ok": bool(d.get("orientation")), "required": True},
        {"item": "Au moins 4 photos", "ok": d.get("photos_count", 0) >= 4, "required": False},
        {"item": "Analyse de sol au laboratoire (recommandée si l'incertitude est forte)",
         "ok": bool(survey.get("lab_soil_analysis")) or not soil_uncertain, "required": False},
    ]
    return {"ready": all(c["ok"] for c in checks if c["required"]),
            "completeness_pct": round(100 * sum(c["ok"] for c in checks) / len(checks)), "checks": checks}


@router.get("/domains/{domain_id}/readiness", summary="Ce qui manque avant de générer le plan")
async def readiness(domain_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    return await _readiness(db, await _domain(db, domain_id))


# --- Plan de mise en valeur ------------------------------------------------------------

async def _market_prices(db, department: str) -> list[dict]:
    """Prix observés sur la plateforme (180 jours) : base économique du plan."""
    since = utcnow() - timedelta(days=180)
    rows = [r async for r in db["market_offers"].aggregate([
        {"$match": {"created_at": {"$gte": since}, "status": {"$in": ["active", "sold"]}}},
        {"$project": {"product": {"$toLower": "$product_name"}, "department": 1,
                      "price": {"$cond": [{"$eq": ["$status", "sold"]}, "$sold_unit_price_fcfa", "$unit_price_fcfa"]}}},
        {"$group": {"_id": "$product", "avg": {"$avg": "$price"}, "n": {"$sum": 1},
                    "local": {"$sum": {"$cond": [{"$eq": ["$department", department]}, 1, 0]}}}},
        {"$sort": {"n": -1}}, {"$limit": 15},
    ])]
    return [{"product": r["_id"], "avg_fcfa_kg": round(r["avg"]), "observations": r["n"], "in_department": r["local"]} for r in rows]


def _plan_prompt(context_json: str) -> str:
    return (
        "Élabore un plan concret de mise en valeur agricole pour une terre du domaine privé de l'État béninois, "
        "attribuée ensuite en concession à un exploitant. Données de la terre (JSON) :\n"
        f"{context_json}\n\n"
        "Exigences :\n"
        "- évalue l'aptitude de 5 à 8 cultures pertinentes pour la zone, en tenant compte des cultures prioritaires "
        "et exclues de l'État, des filières soutenues et des facteurs limitants (sol, eau, relief, accès) ;\n"
        "- propose 2 ou 3 scénarios distincts (vivrier, rente, mixte ou rotation) ; pour chacun : cultures, rotation, "
        "répartition de la surface, rendements en fourchette (kg/ha), coûts et revenus en FCFA/ha (fourchettes, en "
        "t'appuyant sur les prix de marché fournis quand ils existent), investissements, main-d'œuvre, calendrier "
        "cultural aligné sur les saisons des pluies de la zone, avantages et inconvénients ;\n"
        "- indique le scénario recommandé et pourquoi ;\n"
        "- plan de fertilité adapté au sol (amendements, matière organique, légumineuses) ;\n"
        "- risques avec parades ;\n"
        "- indicateurs de mise en valeur mesurables lors des inspections, avec échéance en mois, cohérents avec la part "
        "minimale de mise en valeur demandée ;\n"
        "- liste honnête des données manquantes ou incertaines et niveau de confiance global."
    )


def _plan_context(d: dict, prices: list[dict]) -> dict:
    env = d.get("environment") or {}
    return {
        "terre": {"surface_ha": d["surface_hectares"], "departement": d["department"], "commune": d["commune"],
                  "localite": d.get("locality"), "cultures_jugees_adaptees_par_l_agent": d.get("suitable_crops"),
                  "description": d.get("description")},
        "zone_agroecologique": env.get("zone"),
        "sol": {"source": (env.get("soil") or {}).get("source"), "statut": (env.get("soil") or {}).get("status"),
                "valeurs": (env.get("soil") or {}).get("data"), "lecture": env.get("soil_reading")},
        "climat_10_ans": env.get("climate"),
        "relief": env.get("relief"),
        "accessibilite": env.get("access"),
        "releve_de_terrain": {k: v for k, v in (d.get("survey") or {}).items() if k not in ("surveyed_by", "saved_at")},
        "orientations_etat": {k: v for k, v in (d.get("orientation") or {}).items() if k not in ("set_by", "saved_at")},
        "filieres_soutenues_par_l_etat": settings.subsidized_crops,
        "prix_observes_sur_la_plateforme": prices,
    }


def _sanitize(plan: ValorizationPlan) -> ValorizationPlan:
    plan.recommended_scenario_index = min(plan.recommended_scenario_index, len(plan.scenarios) - 1)
    for sc in plan.scenarios:
        for r in [sc.costs_fcfa_ha, sc.revenue_fcfa_ha] + [y.yield_kg_ha for y in sc.yields]:
            if r.low > r.high:
                r.low, r.high = r.high, r.low
    return plan


def _plan_out(doc: dict) -> dict:
    return serialize_doc(doc)


@router.post("/domains/{domain_id}/plans", status_code=status.HTTP_201_CREATED, response_model=PlanOut,
             summary="Générer un plan de mise en valeur (IA)")
async def generate_plan(domain_id: str, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    d = await _domain(db, domain_id)
    env = d.get("environment")
    if not env or (utcnow() - as_utc(env["fetched_at"])).days > settings.ENVIRONMENT_MAX_AGE_DAYS:
        d["environment"] = await _refresh_environment(db, d)
    check = await _readiness(db, d)
    if not check["ready"]:
        missing = [c["item"] for c in check["checks"] if c["required"] and not c["ok"]]
        raise HTTPException(status_code=422, detail={"message": "Données insuffisantes pour un plan fiable.", "reasons": missing})

    photos = [(bytes(p["data"]), "image/jpeg") async for p in db["domain_photos"].find({"domain_id": domain_id}).limit(PHOTOS_TO_AI)]
    context = _plan_context(d, await _market_prices(db, d["department"]))
    prompt = _plan_prompt(ai_service.to_prompt_json(context))
    if photos:
        prompt += f"\n{len(photos)} photo(s) du terrain sont jointes : tiens compte de ce qu'elles montrent (couvert, sol, eau, relief)."
    plan, run_id = await ai_service.generate(db, purpose="domain_plan", schema=ValorizationPlan, prompt=prompt, parts=photos,
                                             model=settings.GEMINI_PLAN_MODEL, requested_by=agent.npi, temperature=0.4)
    plan = _sanitize(plan)
    version = await db["domain_plans"].count_documents({"domain_id": domain_id}) + 1
    doc = {"domain_id": domain_id, "version": version, "plan": plan.model_dump(mode="json"), "status": "proposition",
           "model": settings.GEMINI_PLAN_MODEL, "ai_run_id": run_id, "created_by": agent.npi, "created_at": utcnow(),
           "data_used": {**env_profile.availability(d["environment"]), "photos": len(photos),
                         "lab_analysis": bool((d.get("survey") or {}).get("lab_soil_analysis")), "readiness_pct": check["completeness_pct"]}}
    doc["_id"] = (await db["domain_plans"].insert_one(doc)).inserted_id
    await db["state_domains"].update_one({"_id": d["_id"]}, {"$set": {"latest_plan_id": str(doc["_id"])}})
    return _plan_out(doc)


@router.get("/domains/{domain_id}/plans", response_model=list[PlanOut])
async def list_plans(domain_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    return [_plan_out(p) async for p in db["domain_plans"].find({"domain_id": domain_id}).sort("version", -1)]


@router.get("/domains/plans/{plan_id}", response_model=PlanOut)
async def get_plan(plan_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    return _plan_out(await ds.get_or_404(db, "domain_plans", plan_id, "Plan"))


@router.patch("/domains/plans/{plan_id}/review", response_model=PlanOut, summary="Relecture par un expert (validation ou demande de révision)")
async def review_plan(plan_id: str, payload: PlanReview, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    p = await ds.get_or_404(db, "domain_plans", plan_id, "Plan")
    if p["created_by"] == agent.npi:
        raise HTTPException(status_code=403, detail="La relecture doit être faite par une autre personne que celle qui a généré le plan.")
    review = {**payload.model_dump(), "recorded_by": agent.npi, "at": utcnow()}
    await db["domain_plans"].update_one({"_id": p["_id"]}, {"$set": {"status": payload.status, "review": review}})
    if payload.status == "valide":
        await db["state_domains"].update_one({"_id": parse_object_id(p["domain_id"])}, {"$set": {"validated_plan_id": plan_id}})
    await db["ai_runs"].update_one({"_id": parse_object_id(p["ai_run_id"])}, {"$set": {"review_status": payload.status}})
    return _plan_out(await db["domain_plans"].find_one({"_id": p["_id"]}))


@router.get("/domains/plans/{plan_id}/call-draft", summary="Préremplir un appel à candidatures depuis le plan")
async def call_draft(plan_id: str, db=Depends(get_database), _: CurrentUser = Depends(AGENT)):
    p = await ds.get_or_404(db, "domain_plans", plan_id, "Plan")
    d = await _domain(db, p["domain_id"])
    plan = ValorizationPlan.model_validate(p["plan"])
    sc = plan.scenarios[plan.recommended_scenario_index]
    crops = list(dict.fromkeys(sc.crops + [s.crop for s in plan.suitability if s.suitability == "elevee"]))
    indicators = "\n".join(f"- **{i.indicator}** : {i.target} (sous {i.deadline_months} mois ; contrôle : {i.how_to_check})"
                           for i in plan.valorization_indicators)
    fertility = "\n".join(f"- {f.action} ({f.timing})" for f in plan.fertility_plan)
    calendar = "\n".join(f"- {c.period} : {c.activity}" for c in sc.calendar)
    min_pct = (d.get("orientation") or {}).get("min_valorization_pct", 80)
    cahier = (
        f"## Obligations de mise en valeur\n\nMettre en valeur au moins {min_pct:.0f} % de la surface.\n\n"
        f"### Indicateurs contrôlés lors des inspections\n{indicators}\n\n"
        f"### Pratiques de fertilité attendues\n{fertility}\n\n"
        f"### Calendrier indicatif (scénario « {sc.name} »)\n{calendar}\n\n"
        "Les cultures et le calendrier peuvent être adaptés par le candidat, à condition de justifier le respect des indicateurs."
    )
    return {
        "plan_id": plan_id,
        "plan_status": p["status"],
        "warning": None if p["status"] == "valide" else "Plan non validé par un expert : à faire relire avant publication.",
        "title": f"Mise en valeur de {d['name']}",
        "description": plan.summary,
        "cahier_des_charges": cahier,
        "allowed_crops": crops[:10],
        "mise_en_valeur_months": max((i.deadline_months for i in plan.valorization_indicators), default=12),
    }


# --- Aide à l'analyse des candidatures --------------------------------------------------

def _yield_check(app_doc: dict, plan: ValorizationPlan | None, surface_ha: float) -> str:
    """Contrôle déterministe : production prévue du candidat face aux fourchettes du plan."""
    if not plan:
        return "Aucun plan de référence : réalisme non évalué."
    crop = app_doc["proposed_crop"].lower()
    ranges = [y.yield_kg_ha for sc in plan.scenarios for y in sc.yields if y.crop.lower() == crop]
    if not ranges:
        return f"La culture proposée ({app_doc['proposed_crop']}) n'apparaît pas dans le plan de référence."
    low, high = min(r.low for r in ranges) * surface_ha, max(r.high for r in ranges) * surface_ha
    planned = app_doc["planned_yield_kg"]
    if planned > high * 1.3:
        return f"Production prévue ({planned:,.0f} kg) nettement au-dessus de la fourchette du plan ({low:,.0f} à {high:,.0f} kg) : optimiste."
    if planned < low * 0.5:
        return f"Production prévue ({planned:,.0f} kg) très en dessous de la fourchette du plan ({low:,.0f} à {high:,.0f} kg)."
    return f"Production prévue ({planned:,.0f} kg) cohérente avec la fourchette du plan ({low:,.0f} à {high:,.0f} kg)."


@router.post("/calls/{call_id}/applications/{application_id}/ai-review", summary="Aide à l'analyse d'une candidature (IA)")
async def review_application(call_id: str, application_id: str, db=Depends(get_database), agent: CurrentUser = Depends(AGENT)):
    call = await ds.get_or_404(db, "calls", call_id, "Appel")
    app_doc = await ds.get_or_404(db, "applications", application_id, "Candidature")
    if app_doc["call_id"] != call_id:
        raise ds.not_found("Candidature")
    plan = None
    if call.get("plan_id"):
        p = await db["domain_plans"].find_one({"_id": parse_object_id(call["plan_id"])})
        plan = ValorizationPlan.model_validate(p["plan"]) if p else None
    check = _yield_check(app_doc, plan, call["surface_hectares"])
    context = {
        "appel": {k: call[k] for k in ("title", "cahier_des_charges", "allowed_crops", "duration_years", "mise_en_valeur_months", "surface_hectares")},
        "plan_de_reference": plan.model_dump(include={"summary", "scenarios", "valorization_indicators", "risks"}) if plan else None,
        "candidature": {k: app_doc.get(k) for k in ("proposed_crop", "planned_yield_kg", "motivation", "experience_years")},
        "score_du_candidat": {"score": app_doc["score_at_submission"],
                              "criteres": [{k: c[k] for k in ("label", "score", "detail")} for c in app_doc.get("score_components", [])]},
        "controle_automatique_du_rendement": check,
    }
    prompt = ("Aide un agent de l'État à analyser une candidature à une concession agricole. Compare le projet au plan de "
              "référence et au cahier des charges. Sois factuel et équitable ; ne recommande pas d'attribuer ou de rejeter : "
              "liste les points forts, les écarts, les risques et les questions à poser au candidat.\n"
              + ai_service.to_prompt_json(context))
    review, run_id = await ai_service.generate(db, purpose="application_review", schema=ApplicationReview, prompt=prompt, requested_by=agent.npi)
    out = {**review.model_dump(), "yield_check": check, **ai_service.ai_meta(run_id),
           "disclaimer": "Aide à l'analyse : ne remplace ni le classement officiel ni l'évaluation de l'agent."}
    await db["applications"].update_one({"_id": app_doc["_id"]}, {"$set": {"ai_review": out}})
    return out
