"""Service d'IA centralisé : toutes les fonctions d'assistance passent par ici.

Garanties :
- **l'IA propose, l'humain décide** : chaque sortie est journalisée comme « proposition » avec le
  modèle, la date et l'empreinte des données utilisées, pour pouvoir expliquer une décision après coup ;
- **pas de données personnelles envoyées à Gemini** : les contextes sont nettoyés (NPI, noms, téléphones) ;
- **coûts maîtrisés** : cache des réponses identiques et quota quotidien par utilisateur.
"""
import hashlib
import json
import logging
from datetime import timedelta
from typing import TypeVar

from fastapi import HTTPException, status
from google.genai import types
from pydantic import BaseModel

from app.core import ai
from app.core.config import settings
from app.core.utils import utcnow

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

SYSTEM_INSTRUCTION = (
    "Tu es un agronome expérimenté du Bénin, au service d'une plateforme publique. Règles impératives : "
    "1) appuie-toi uniquement sur les données fournies et sur des connaissances agronomiques établies ; "
    "2) donne des fourchettes plutôt que des valeurs uniques, et signale explicitement les données manquantes "
    "ou incertaines ; 3) privilégie les pratiques durables, la matière organique, les rotations et les solutions "
    "biologiques locales ; 4) ne recommande jamais un pesticide interdit ; pour tout produit chimique, renvoie vers "
    "un produit homologué au Bénin et vers le conseiller agricole ; 5) écris en français clair, phrases courtes ; "
    "6) tu proposes, tu ne décides pas : tes sorties seront relues par un agent ou un expert."
)

# Clés retirées de tout contexte avant envoi à l'IA
PERSONAL_KEYS = {
    "npi", "farmer_npi", "npi_owner", "buyer_npi", "from_npi", "new_owner_npi", "parties_npi", "reported_by",
    "phone", "contact_phone", "buyer_phone", "full_name", "farmer_name", "buyer_name", "created_by", "handled_by",
    "decided_by", "proposed_by", "approved_by", "inspector_npi", "recorded_by", "verified_by", "published_by",
    "by", "original_filename", "_id",
}


def strip_personal(value):
    """Retire récursivement les données personnelles d'un contexte."""
    if isinstance(value, dict):
        return {k: strip_personal(v) for k, v in value.items() if k not in PERSONAL_KEYS}
    if isinstance(value, list):
        return [strip_personal(v) for v in value]
    return value


def to_prompt_json(context: dict) -> str:
    return json.dumps(strip_personal(context), ensure_ascii=False, default=str, indent=1)


def _digest(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode())
    return h.hexdigest()


async def _check_quota(db, npi: str | None) -> None:
    if not npi:
        return
    since = utcnow() - timedelta(hours=24)
    used = await db["ai_runs"].count_documents({"requested_by": npi, "cached": False, "created_at": {"$gte": since}})
    if used >= settings.AI_DAILY_QUOTA_PER_USER:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Quota quotidien d'assistance IA atteint. Réessayez demain.")


def require_ai() -> None:
    if ai.ai_client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Assistance IA indisponible : clé Gemini non configurée.")


async def generate(
    db,
    *,
    purpose: str,
    schema: type[T],
    prompt: str,
    parts: list[tuple[bytes, str]] | None = None,
    model: str | None = None,
    requested_by: str | None = None,
    temperature: float = 0.3,
    use_cache: bool = True,
) -> tuple[T, str]:
    """Génère une sortie structurée validée par `schema`. Renvoie (résultat, identifiant du journal)."""
    require_ai()
    model = model or settings.GEMINI_MODEL
    parts = parts or []
    key = _digest(model, purpose, schema.__name__, SYSTEM_INSTRUCTION, prompt, *[d for d, _ in parts])

    if use_cache:
        hit = await db["ai_cache"].find_one({"_id": key})
        if hit and hit["created_at"] and (utcnow() - _aware(hit["created_at"])).days < settings.AI_CACHE_DAYS:
            res = await db["ai_runs"].insert_one(_run_doc(purpose, model, key, hit["output"], requested_by, cached=True))
            return schema.model_validate(hit["output"]), str(res.inserted_id)

    await _check_quota(db, requested_by)
    contents: list = [prompt] + [types.Part.from_bytes(data=d, mime_type=m) for d, m in parts]
    try:
        response = await ai.ai_client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=schema,
                temperature=temperature,
            ),
        )
        output = response.parsed if isinstance(response.parsed, schema) else schema.model_validate_json(response.text)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Échec de l'IA (%s)", purpose)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Le service d'IA est momentanément indisponible.")

    data = output.model_dump(mode="json")
    await db["ai_cache"].update_one({"_id": key}, {"$set": {"output": data, "created_at": utcnow()}}, upsert=True)
    res = await db["ai_runs"].insert_one(_run_doc(purpose, model, key, data, requested_by, cached=False))
    return output, str(res.inserted_id)


def _aware(dt):
    from app.core.utils import as_utc
    return as_utc(dt)


def _run_doc(purpose, model, digest, output, requested_by, cached: bool) -> dict:
    return {"purpose": purpose, "model": model, "input_digest": digest, "output": output, "requested_by": requested_by,
            "cached": cached, "review_status": "proposition", "created_at": utcnow()}


def ai_meta(run_id: str, model: str | None = None) -> dict:
    """Métadonnées jointes à chaque sortie d'IA affichée."""
    return {"ai_run_id": run_id, "model": model or settings.GEMINI_MODEL, "generated_at": utcnow(),
            "status": "proposition", "disclaimer": "Proposition générée par l'IA, à valider par un agent ou un expert."}
