import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.errors import DuplicateKeyError

from pydantic import BaseModel, Field

from app.core import ai_service, tts
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, require_roles
from app.core.utils import utcnow
from app.modules.knowledge.schemas import CATEGORY_INFO, GuideBase, GuideCategory, GuideCreate, GuideOut
from app.modules.monitoring.schemas import LANGUAGES

router = APIRouter(prefix="/knowledge", tags=["Information & Réglementation"])


def _out(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


async def _get_or_404(db, slug: str) -> dict:
    doc = await db["guides"].find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiche introuvable.")
    return doc


@router.get("/categories", summary="Catégories avec libellé et pictogramme")
async def list_categories(db=Depends(get_database)):
    counts = {r["_id"]: r["n"] async for r in db["guides"].aggregate([{"$group": {"_id": "$category", "n": {"$sum": 1}}}])}
    return [{"id": c.value, **CATEGORY_INFO[c], "count": counts.get(c.value, 0)} for c in GuideCategory]


@router.get("/guides", response_model=list[GuideOut], summary="Fiches pratiques (public)")
async def list_guides(
    db=Depends(get_database),
    category: Optional[GuideCategory] = None,
    crop: Optional[str] = Query(None, max_length=60),
    q: Optional[str] = Query(None, max_length=100, description="Recherche dans le titre et le résumé"),
    verified_only: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    filters: dict = {}
    if category:
        filters["category"] = category.value
    if crop:
        # Fiches de la culture demandée, ou valables pour toutes les cultures
        filters["$or"] = [{"crops": {"$regex": f"^{re.escape(crop)}$", "$options": "i"}}, {"crops": {"$size": 0}}]
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        filters.setdefault("$and", []).append({"$or": [{"title": rx}, {"summary": rx}]})
    if verified_only:
        filters["verified"] = True
    cursor = db["guides"].find(filters).sort("title", 1).skip(skip).limit(limit)
    return [_out(d) async for d in cursor]


@router.get("/guides/{slug}", response_model=GuideOut)
async def get_guide(slug: str, db=Depends(get_database)):
    return _out(await _get_or_404(db, slug))


class GuideAudioSummary(BaseModel):
    summary: str = Field(..., description="Résumé clair et simple en 2 à 3 phrases dans la langue cible pour lecture vocale aux paysans")


@router.get("/guides/{slug}/audio", response_class=Response, responses=tts.AUDIO_RESPONSES, summary="Lecture audio de la fiche")
async def get_guide_audio(
    slug: str,
    format: tts.AudioFormat = "mp3",
    language: Optional[str] = Query(None, description="Langue de synthèse vocale (fr, fon, yo, en)"),
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    doc = await _get_or_404(db, slug)
    if not language:
        profile = await db["users"].find_one({"npi": user.npi}, {"preferred_language": 1})
        language = (profile or {}).get("preferred_language", "fr")

    if language in ("fon", "yo", "en"):
        prompt = (
            f"Tu es un agronome au Bénin. Traduis et adapte pour les exploitants agricoles cette fiche pratique en langue {LANGUAGES.get(language, language)}.\n"
            f"Fais un résumé simple, bienveillant, de 2 à 3 phrases claires faciles à comprendre à l'écoute vocale :\n"
            f"Titre : {doc['title']}\n"
            f"Résumé : {doc['summary']}\n"
            f"Étapes : {' '.join(doc.get('steps') or [])}"
        )
        try:
            res, _ = await ai_service.generate(
                db, purpose="guide_audio_translation", schema=GuideAudioSummary, prompt=prompt, requested_by=user.npi, temperature=0.2
            )
            text = res.summary
        except Exception:
            text = f"{doc['title']}. {doc['summary']}"
    else:
        text = f"{doc['title']}. {doc['summary']} " + " ".join(doc.get("steps") or [])

    return await tts.audio_response(db, text, format, "public, max-age=604800", language=language)


@router.post("/guides", status_code=status.HTTP_201_CREATED, response_model=GuideOut)
async def create_guide(payload: GuideCreate, db=Depends(get_database), agent: CurrentUser = Depends(require_roles("state_agent"))):
    doc = {**payload.model_dump(mode="json"), "updated_at": utcnow(), "updated_by": agent.npi}
    try:
        await db["guides"].insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Une fiche avec cet identifiant existe déjà.")
    return _out(doc)


@router.put("/guides/{slug}", response_model=GuideOut)
async def update_guide(slug: str, payload: GuideBase, db=Depends(get_database), agent: CurrentUser = Depends(require_roles("state_agent"))):
    await _get_or_404(db, slug)
    changes = {**payload.model_dump(mode="json"), "updated_at": utcnow(), "updated_by": agent.npi}
    await db["guides"].update_one({"slug": slug}, {"$set": changes})
    return _out(await _get_or_404(db, slug))


@router.delete("/guides/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_guide(slug: str, db=Depends(get_database), _: CurrentUser = Depends(require_roles("state_agent"))):
    res = await db["guides"].delete_one({"slug": slug})
    if not res.deleted_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiche introuvable.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/guides/{slug}/verify", response_model=GuideOut, summary="Valider ou invalider une fiche pratique / réglementation")
async def toggle_guide_verification(
    slug: str,
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    doc = await _get_or_404(db, slug)
    new_verified = not doc.get("verified", False)
    await db["guides"].update_one(
        {"slug": slug},
        {"$set": {"verified": new_verified, "updated_at": utcnow(), "verified_by": agent.npi if new_verified else None}},
    )
    doc["verified"] = new_verified
    doc["updated_at"] = utcnow()
    doc["verified_by"] = agent.npi if new_verified else None
    return _out(doc)
