import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pymongo.errors import DuplicateKeyError

from app.core import tts
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, require_roles
from app.core.utils import utcnow
from app.modules.knowledge.schemas import CATEGORY_INFO, GuideBase, GuideCategory, GuideCreate, GuideOut

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


@router.get(
    "/guides/{slug}/audio",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}}}},
    summary="Lecture audio de la fiche",
)
async def get_guide_audio(slug: str, db=Depends(get_database), _: CurrentUser = Depends(get_current_user)):
    doc = await _get_or_404(db, slug)
    text = f"{doc['title']}. {doc['summary']} " + " ".join(doc.get("steps") or [])
    wav = await tts.synthesize_wav(db, text)
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "public, max-age=604800"})


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
