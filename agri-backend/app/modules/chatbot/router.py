"""API REST pour le Chatbot Intelligent Multilingue (texte et voix)."""
import json
import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.core import tts
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, get_optional_user
from app.core.utils import parse_object_id, serialize_doc
from app.modules.chatbot.service import AUDIO_TYPES, MAX_AUDIO_BYTES, ask_chatbot, transcribe_voice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chatbot", tags=["Chatbot Intelligent"])
Language = Literal["fr", "fon", "yo", "en"]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatMessage] = Field(default_factory=list)
    language: Optional[Language] = None
    force_web_search: bool = False


async def _resolve_lang(db, user: CurrentUser | None, requested: str | None) -> str:
    if requested:
        return requested
    if user:
        profile = await db["users"].find_one({"npi": user.npi}, {"preferred_language": 1})
        if profile and profile.get("preferred_language"):
            return profile["preferred_language"]
    return "fr"


@router.post("/message", summary="Envoyer un message au chatbot (texte)")
async def send_message(
    payload: ChatInput,
    db=Depends(get_database),
    user: CurrentUser | None = Depends(get_optional_user),
):
    lang = await _resolve_lang(db, user, payload.language)
    history_dicts = [{"role": m.role, "content": m.content} for m in payload.history]
    return await ask_chatbot(
        db,
        user,
        payload.message,
        history=history_dicts,
        language=lang,
        force_web_search=payload.force_web_search,
    )


@router.post("/message-voice", summary="Envoyer un message vocal au chatbot (audio)")
async def send_voice_message(
    file: UploadFile = File(..., description="Fichier audio de question vocale (60 s max)"),
    history: Optional[str] = Form(None, description="Historique JSON de conversation"),
    language: Optional[Language] = Form(None),
    force_web_search: bool = Form(False),
    db=Depends(get_database),
    user: CurrentUser | None = Depends(get_optional_user),
):
    mime = (file.content_type or "").split(";")[0]
    if mime not in AUDIO_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Format audio non pris en charge.")

    data = await file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Enregistrement audio trop volumineux (4 Mo max).")

    # Transcription STT
    transcript = await transcribe_voice(db, user, data, mime)
    if len(transcript) < 2:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message vocal inaudible. Veuillez répéter.")

    history_list = []
    if history:
        try:
            parsed = json.loads(history)
            if isinstance(parsed, list):
                history_list = parsed
        except Exception:
            pass

    lang = await _resolve_lang(db, user, language)
    res = await ask_chatbot(
        db,
        user,
        transcript,
        history=history_list,
        language=lang,
        force_web_search=force_web_search,
    )
    return {**res, "user_transcript": transcript}


@router.get("/audio/{message_id}", response_class=Response, responses=tts.AUDIO_RESPONSES, summary="Écouter la réponse vocale du chatbot")
async def get_message_audio(
    message_id: str,
    format: tts.AudioFormat = "mp3",
    db=Depends(get_database),
    user: CurrentUser | None = Depends(get_optional_user),
):
    doc = await db["chatbot_messages"].find_one({"_id": parse_object_id(message_id, "Message")})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message introuvable.")

    lang = doc.get("language", "fr")
    text_to_speak = doc.get("audio_summary") or doc.get("answer", "")
    return await tts.audio_response(db, text_to_speak, format, "public, max-age=604800", language=lang)


@router.get("/history", summary="Historique récent des messages du chatbot")
async def get_history(
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_database),
    user: CurrentUser | None = Depends(get_optional_user),
):
    if not user:
        return []
    cursor = db["chatbot_messages"].find({"npi": user.npi}).sort("created_at", -1).limit(limit)
    return [serialize_doc(d) async for d in cursor]
