"""Assistant agricole : répond aux questions (texte ou voix) à partir des fiches pratiques validées."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from app.core import ai_service, tts
from app.core.config import settings
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user
from app.core.utils import parse_object_id, serialize_doc, utcnow
from app.modules.assistant.retrieval import rank
from app.modules.monitoring.schemas import LANGUAGES

router = APIRouter(prefix="/assistant", tags=["Assistant agricole"])
Language = Literal["fr", "fon", "yo", "en"]
AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/x-m4a", "audio/aac"}
MAX_AUDIO_BYTES = 3 * 1024 * 1024
NOT_COVERED_MAP = {
    "fr": ("Je n'ai pas encore de fiche validée sur cette question. Posez-la à votre conseiller agricole, "
           "ou consultez les fiches pratiques disponibles."),
    "fon": ("Un kɔn nǔ mɛɖé mɛtɔn ɖe ɖo wema lɛ mɛ á. Kànbyɔ mɛ e nɔ na wěɖexámɛ lɛ́, alǒ kpɔ́n wema ɖěɖee ɖè lɛ́."),
    "yo": ("Kò tíì sí ìwé tó fọwọ́sí lórí ìbéèrè yìí. Bèrè lọ́wọ́ olùbádámọ̀ràn oko rẹ, tàbí wo àwọn ìwé tó wà."),
    "en": ("I do not have a validated guide on this question yet. Please ask your agricultural advisor, "
           "or consult the available practical guides."),
}
NOT_COVERED = NOT_COVERED_MAP["fr"]


class AskInput(BaseModel):
    question: str = Field(..., min_length=5, max_length=1000)
    language: Optional[Language] = None
    land_id: Optional[str] = None


class AssistantAnswer(BaseModel):
    covered: bool = Field(..., description="Faux si les fiches fournies ne permettent pas de répondre")
    answer: str
    simple_summary: str = Field(..., description="1 à 2 phrases simples, dans la langue demandée, pour lecture audio")
    used_sources: list[str] = Field(default_factory=list, description="Identifiants (slug) des fiches utilisées")
    follow_up: Optional[str] = Field(None, description="Conseil de suivi, par ex. voir un conseiller")


class Transcript(BaseModel):
    transcript: str
    language_detected: Optional[str] = None


async def _language(db, user: CurrentUser, requested: str | None) -> str:
    if requested:
        return requested
    profile = await db["users"].find_one({"npi": user.npi}, {"preferred_language": 1})
    return (profile or {}).get("preferred_language", "fr")


async def _answer(db, user: CurrentUser, question: str, language: str, land_id: str | None, transcript: bool = False) -> dict:
    filters = {} if settings.ASSISTANT_INCLUDE_UNVERIFIED else {"verified": True}
    guides = [g async for g in db["guides"].find(filters)]
    sources = rank(question, guides)
    context_land = None
    if land_id:
        land = await db["lands"].find_one({"_id": parse_object_id(land_id, "Parcelle"), "npi_owner": user.npi})
        if land:
            context_land = {"culture": land["crop_type"], "departement": land["department"], "commune": land["commune"]}

    if not sources:
        msg = NOT_COVERED_MAP.get(language, NOT_COVERED)
        out = AssistantAnswer(covered=False, answer=msg, simple_summary=msg, used_sources=[])
        meta = {"ai_run_id": None, "status": "sans_ia"}
    else:
        fiches = [{"slug": g["slug"], "titre": g["title"], "resume": g["summary"], "etapes": g.get("steps"),
                   "contenu": g.get("content", "")[:4000], "validee": g.get("verified", False), "source": g.get("source")}
                  for g in sources]
        prompt = (
            "Réponds à la question d'un exploitant béninois en t'appuyant EXCLUSIVEMENT sur les fiches ci-dessous. "
            "Si elles ne permettent pas de répondre, mets covered=false et invite à consulter un conseiller agricole ; "
            "n'invente rien. Cite dans used_sources les slugs réellement utilisés. Réponse courte, concrète, en étapes simples. "
            f"Rédige simple_summary en {LANGUAGES.get(language, 'français')} ; le reste en français.\n"
            f"Question : {question}\n"
            f"Contexte de la parcelle : {ai_service.to_prompt_json(context_land or {})}\n"
            f"Fiches : {ai_service.to_prompt_json({'fiches': fiches})}"
        )
        out, run_id = await ai_service.generate(db, purpose="assistant", schema=AssistantAnswer, prompt=prompt, requested_by=user.npi, temperature=0.2)
        allowed = {g["slug"] for g in sources}
        out.used_sources = [s for s in out.used_sources if s in allowed]  # pas de source inventée
        if out.covered and not out.used_sources:
            out.used_sources = [sources[0]["slug"]]
        meta = ai_service.ai_meta(run_id)

    by_slug = {g["slug"]: g for g in sources}
    doc = {"npi": user.npi, "question": question, "language": language, "via_voice": transcript,
           **out.model_dump(), "sources": [{"slug": s, "title": by_slug[s]["title"], "verified": by_slug[s].get("verified", False),
                                            "source": by_slug[s].get("source")} for s in out.used_sources],
           **meta, "created_at": utcnow()}
    doc["_id"] = (await db["assistant_logs"].insert_one(doc)).inserted_id
    out_doc = serialize_doc({k: v for k, v in doc.items() if k != "npi"})
    out_doc["audio_url"] = f"{settings.API_V1_STR}/assistant/answers/{out_doc['id']}/audio"
    return out_doc


@router.post("/ask", summary="Poser une question écrite")
async def ask(payload: AskInput, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    return await _answer(db, user, payload.question, await _language(db, user, payload.language), payload.land_id)


@router.post("/ask-voice", summary="Poser une question à l'oral (enregistrement audio)")
async def ask_voice(
    file: UploadFile = File(..., description="Enregistrement de 60 s maximum (webm, ogg, mp3, m4a, wav)"),
    language: Optional[Language] = Form(None),
    land_id: Optional[str] = Form(None),
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    mime = (file.content_type or "").split(";")[0]
    if mime not in AUDIO_TYPES:
        raise HTTPException(status_code=415, detail="Format audio non pris en charge.")
    data = await file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Enregistrement trop long (3 Mo maximum).")
    transcript, _ = await ai_service.generate(
        db, purpose="assistant_transcription", schema=Transcript, parts=[(data, mime)], requested_by=user.npi, temperature=0,
        prompt="Transcris fidèlement la question posée dans cet enregistrement (français ou langue locale du Bénin). "
               "Si elle n'est pas en français, donne aussi la traduction française dans transcript.",
    )
    if len(transcript.transcript.strip()) < 5:
        raise HTTPException(status_code=422, detail="Question inaudible : réessayez dans un endroit plus calme.")
    out = await _answer(db, user, transcript.transcript, await _language(db, user, language), land_id, transcript=True)
    return {**out, "transcript": transcript.transcript}


@router.get("/history", summary="Mes questions précédentes")
async def history(db=Depends(get_database), user: CurrentUser = Depends(get_current_user), limit: int = Query(20, ge=1, le=100)):
    return [serialize_doc(d) async for d in db["assistant_logs"].find({"npi": user.npi}, {"npi": 0}).sort("created_at", -1).limit(limit)]


@router.get("/answers/{answer_id}/audio", response_class=Response, responses=tts.AUDIO_RESPONSES)
async def answer_audio(answer_id: str, format: tts.AudioFormat = "mp3", db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    doc = await db["assistant_logs"].find_one({"_id": parse_object_id(answer_id, "Réponse"), "npi": user.npi})
    if not doc:
        raise HTTPException(status_code=404, detail="Réponse introuvable.")
    return await tts.audio_response(db, doc["simple_summary"], format, "private, max-age=604800")
