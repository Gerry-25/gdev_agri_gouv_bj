"""Agronomie de la parcelle : profil de sol et plan de fumure assisté par l'IA."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.core import ai_service, geo, tts
from app.core.database import get_database
from app.core.environment import profile as env_profile
from app.core.environment import soil as soil_env
from app.core.security import CurrentUser, get_current_user
from app.core.utils import serialize_doc, utcnow
from app.modules.lands.service import ensure_owner, ensure_owner_or_agent, get_land_or_404
from app.modules.monitoring.schemas import LANGUAGES

router = APIRouter(tags=["Agronomie de la parcelle"])


class Range(BaseModel):
    low: float = Field(..., ge=0)
    high: float = Field(..., ge=0)


class SoilFinding(BaseModel):
    parameter: str
    level: str
    comment: str


class Input(BaseModel):
    product: str
    dose: str = Field(..., description="Dose et unité, ex. « 150 kg/ha »")
    timing: str
    rationale: str


class FertilizationPlan(BaseModel):
    simple_summary: str = Field(..., description="2 phrases très simples, pour lecture audio")
    soil_diagnosis: list[SoilFinding]
    amendments: list[Input]
    organic_inputs: list[Input]
    mineral_inputs: list[Input] = Field(..., description="Uniquement des engrais homologués courants au Bénin")
    rotation_advice: str
    expected_yield_kg_ha: Range
    cost_estimate_fcfa_ha: Range
    warnings: list[str]


class FertilizationRequest(BaseModel):
    crop_type: Optional[str] = Field(None, min_length=2, max_length=60, description="Par défaut : culture de la parcelle")
    target_yield_kg_ha: Optional[float] = Field(None, gt=0)
    organic_resources: list[Literal["fumier", "compost", "residus_culture", "cendre", "fientes", "aucune"]] = Field(default_factory=list)
    budget_level: Literal["faible", "moyen", "eleve"] = "moyen"


async def _soil(db, land: dict, refresh: bool = False) -> dict:
    if land.get("environment") and not refresh:
        return land["environment"]
    poly = geo.from_geojson(land["boundary"])
    env = await env_profile.collect(poly, land["department"], land["commune"], full=False)
    await db["lands"].update_one({"_id": land["_id"]}, {"$set": {"environment": env, "updated_at": utcnow()}})
    return env


@router.post("/lands/{land_id}/soil", summary="Collecter le sol et le climat de la parcelle")
async def refresh_soil(land_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await get_land_or_404(db, land_id)
    ensure_owner_or_agent(land, user)
    env = await _soil(db, land, refresh=True)
    return {"environment": env, "reading": env["soil_reading"]}


@router.get("/lands/{land_id}/soil", summary="Lecture simple du sol (sans IA)")
async def get_soil(land_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await get_land_or_404(db, land_id)
    ensure_owner_or_agent(land, user)
    env = await _soil(db, land)
    return {"environment": env, "reading": env["soil_reading"]}


@router.post("/lands/{land_id}/fertilization-plans", status_code=201, summary="Plan de fumure adapté au sol (IA)")
async def fertilization_plan(land_id: str, payload: FertilizationRequest, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await get_land_or_404(db, land_id)
    ensure_owner(land, user)
    env = await _soil(db, land)
    crop = payload.crop_type or land["crop_type"]
    harvests = [{"saison": h["season"], "culture": h["crop_type"], "kg_ha": round(h["actual_yield_kg"] / land["surface_hectares"])}
                async for h in db["harvests"].find({"land_id": land_id}).sort("season", -1).limit(6)]
    context = {
        "parcelle": {"surface_ha": land["surface_hectares"], "departement": land["department"], "commune": land["commune"], "culture": crop},
        "zone_agroecologique": env.get("zone"),
        "sol": (env.get("soil") or {}).get("data"), "statut_donnees_sol": (env.get("soil") or {}).get("status"),
        "lecture_du_sol": env.get("soil_reading"),
        "climat": (env.get("climate") or {}).get("data"),
        "recoltes_passees": harvests,
        "objectif_rendement_kg_ha": payload.target_yield_kg_ha,
        "ressources_organiques_disponibles": payload.organic_resources,
        "budget": payload.budget_level,
    }
    prompt = ("Établis un plan de fumure pour cette parcelle de petit exploitant béninois. Adapte-le au sol réel et au budget ; "
              "valorise d'abord les ressources organiques disponibles ; propose des doses prudentes, fractionnées, avec les "
              "périodes d'apport alignées sur les saisons des pluies. Si les données de sol manquent ou sont incertaines, "
              "dis-le dans les avertissements et reste générique.\n" + ai_service.to_prompt_json(context))
    plan, run_id = await ai_service.generate(db, purpose="fertilization_plan", schema=FertilizationPlan, prompt=prompt, requested_by=user.npi)
    doc = {"land_id": land_id, "crop_type": crop, "request": payload.model_dump(), "plan": plan.model_dump(),
           **ai_service.ai_meta(run_id), "npi_owner": land["npi_owner"], "created_at": utcnow()}
    doc["_id"] = (await db["fertilization_plans"].insert_one(doc)).inserted_id
    return serialize_doc({k: v for k, v in doc.items() if k != "npi_owner"})


@router.get("/lands/{land_id}/fertilization-plans")
async def list_fertilization_plans(land_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await get_land_or_404(db, land_id)
    ensure_owner_or_agent(land, user)
    return [serialize_doc(d) async for d in db["fertilization_plans"].find({"land_id": land_id}, {"npi_owner": 0}).sort("created_at", -1)]


class FertAudioSummary(BaseModel):
    summary: str = Field(..., description="Résumé simple du plan de fumure pour lecture audio aux paysans")


@router.get("/lands/{land_id}/fertilization-plans/latest/audio", response_class=Response,
            responses=tts.AUDIO_RESPONSES, summary="Écouter le dernier plan de fumure")
async def fertilization_audio(
    land_id: str,
    format: tts.AudioFormat = Query("mp3"),
    language: Optional[str] = Query(None, description="Langue de synthèse vocale (fr, fon, yo, en)"),
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    land = await get_land_or_404(db, land_id)
    ensure_owner_or_agent(land, user)
    doc = await db["fertilization_plans"].find_one({"land_id": land_id}, sort=[("created_at", -1)])
    if not doc:
        from app.modules.domains.service import not_found
        raise not_found("Plan de fumure")
    p = doc["plan"]
    if not language:
        profile = await db["users"].find_one({"npi": user.npi}, {"preferred_language": 1})
        language = (profile or {}).get("preferred_language", "fr")

    if language in ("fon", "yo", "en"):
        prompt = (
            f"Tu es un agronome au Bénin. Traduis et adapte pour les exploitants agricoles ce plan de fumure en langue {LANGUAGES.get(language, language)}.\n"
            f"Fais un résumé simple et encourageant de 2 phrases claires faciles à comprendre à l'écoute vocale :\n"
            f"Culture : {doc.get('crop_type', '')}\n"
            f"Résumé : {p.get('simple_summary', '')}\n"
            f"Conseil : {p.get('rotation_advice', '')}"
        )
        try:
            res, _ = await ai_service.generate(
                db, purpose="fertilization_audio_translation", schema=FertAudioSummary, prompt=prompt, requested_by=user.npi, temperature=0.2
            )
            text = res.summary
        except Exception:
            text = p.get("simple_summary", "")
    else:
        steps = ". ".join(f"{i['product']}, {i['dose']}, {i['timing']}" for i in p.get("organic_inputs", []) + p.get("mineral_inputs", []))
        text = f"{p['simple_summary']}. {steps}"

    return await tts.audio_response(db, text, format, "private, max-age=604800", language=language)
