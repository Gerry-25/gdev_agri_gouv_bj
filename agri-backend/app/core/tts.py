"""Synthèse vocale (Gemini TTS) avec cache MongoDB, pour les exploitants qui lisent difficilement."""
import hashlib
import io
import logging
import wave

from fastapi import HTTPException, status
from google.genai import types

from app.core import ai
from app.core.config import settings
from app.core.utils import utcnow

logger = logging.getLogger(__name__)

# Format renvoyé par Gemini TTS : PCM 16 bits, mono, 24 kHz
_SAMPLE_RATE = 24_000
_MAX_CACHED_BYTES = 12 * 1024 * 1024


def pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


async def synthesize_wav(db, text: str) -> bytes:
    if ai.ai_client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Lecture audio indisponible : clé Gemini non configurée.")

    text = " ".join(text.split())[: settings.TTS_MAX_CHARS]
    key = hashlib.sha256(f"{settings.GEMINI_TTS_MODEL}|{settings.TTS_VOICE}|{text}".encode()).hexdigest()

    cached = await db["audio_cache"].find_one({"_id": key})
    if cached:
        return bytes(cached["wav"])

    try:
        response = await ai.ai_client.aio.models.generate_content(
            model=settings.GEMINI_TTS_MODEL,
            contents=f"Lis ce texte lentement, clairement et avec bienveillance : {text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=settings.TTS_VOICE)
                    )
                ),
            ),
        )
        pcm = response.candidates[0].content.parts[0].inline_data.data
    except Exception:
        logger.exception("Échec de la synthèse vocale")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Le service de lecture audio est indisponible.")

    wav = pcm_to_wav(pcm)
    if len(wav) <= _MAX_CACHED_BYTES:
        await db["audio_cache"].update_one({"_id": key}, {"$set": {"wav": wav, "created_at": utcnow()}}, upsert=True)
    return wav
