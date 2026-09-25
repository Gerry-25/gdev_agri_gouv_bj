"""Synthèse vocale (Gemini TTS) avec cache MongoDB, pour les exploitants qui lisent difficilement.

L'audio est livré en MP3 32 kbit/s par défaut (≈ 4 Ko/s, adapté aux connexions faibles),
ou en WAV sur demande.
"""
import hashlib
import io
import logging
import wave
from typing import Literal

import lameenc
from fastapi import HTTPException, Response, status
from google.genai import types

from app.core import ai
from app.core.config import settings
from app.core.utils import utcnow

logger = logging.getLogger(__name__)

AudioFormat = Literal["mp3", "wav"]
MEDIA_TYPES = {"mp3": "audio/mpeg", "wav": "audio/wav"}

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


def pcm_to_mp3(pcm: bytes) -> bytes:
    enc = lameenc.Encoder()
    enc.set_bit_rate(32)
    enc.set_in_sample_rate(_SAMPLE_RATE)
    enc.set_channels(1)
    enc.set_quality(2)
    return bytes(enc.encode(pcm) + enc.flush())


async def synthesize(db, text: str, fmt: AudioFormat = "mp3", language: str = "fr") -> bytes:
    if ai.ai_client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Lecture audio indisponible : clé Gemini non configurée.")

    text = " ".join(text.split())[: settings.TTS_MAX_CHARS]
    key = hashlib.sha256(f"{settings.GEMINI_TTS_MODEL}|{settings.TTS_VOICE}|{fmt}|{language}|{text}".encode()).hexdigest()

    cached = await db["audio_cache"].find_one({"_id": key})
    if cached:
        return bytes(cached["data"])

    prompt_by_lang = {
        "fon": f"Read and pronounce this text clearly, naturally and authentically in Fon (fɔngbè) language of Benin: {text}",
        "yo": f"Read and pronounce this text clearly, naturally and authentically in Yoruba language: {text}",
        "en": f"Read this text clearly, slowly and kindly: {text}",
        "fr": f"Lis ce texte lentement, clairement et avec bienveillance : {text}",
    }
    instruction = prompt_by_lang.get(language, prompt_by_lang["fr"])

    try:
        response = await ai.ai_client.aio.models.generate_content(
            model=settings.GEMINI_TTS_MODEL,
            contents=instruction,
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

    audio = pcm_to_mp3(pcm) if fmt == "mp3" else pcm_to_wav(pcm)
    if len(audio) <= _MAX_CACHED_BYTES:
        await db["audio_cache"].update_one(
            {"_id": key},
            {"$set": {"data": audio, "format": fmt, "language": language, "created_at": utcnow()}},
            upsert=True,
        )
    return audio


async def audio_response(db, text: str, fmt: AudioFormat, cache_control: str, language: str = "fr") -> Response:
    data = await synthesize(db, text, fmt, language=language)
    return Response(content=data, media_type=MEDIA_TYPES[fmt], headers={"Cache-Control": cache_control})


AUDIO_RESPONSES = {200: {"content": {"audio/mpeg": {}, "audio/wav": {}}}}
