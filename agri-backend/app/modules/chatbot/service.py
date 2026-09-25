"""Service du Chatbot Intelligent :
Combine les données internes (fiches agricoles, parcelles de l'exploitant, marché, alertes)
et une recherche web en direct (actualités agricoles, cours, météo, encyclopédie) si nécessaire,
avec synthèse vocale multilingue (Français, Fon, Yorùbá, Anglais).
"""
import html
import logging
import re
import xml.etree.ElementTree as ET
from typing import List, Optional

import httpx
from pydantic import BaseModel, Field

from app.core import ai, ai_service, tts
from app.core.config import settings
from app.core.utils import serialize_doc, utcnow
from app.modules.assistant.retrieval import rank
from app.modules.monitoring.schemas import LANGUAGES

logger = logging.getLogger(__name__)

AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/x-m4a", "audio/aac"}
MAX_AUDIO_BYTES = 4 * 1024 * 1024


class SourceItem(BaseModel):
    source_type: str = Field(..., description="database ou web")
    title: str
    url: Optional[str] = None
    snippet: Optional[str] = None


class ChatbotResponseSchema(BaseModel):
    answer: str = Field(..., description="Réponse complète et bienveillante en Markdown adaptée aux agriculteurs du Bénin")
    audio_summary: str = Field(..., description="1 à 2 phrases simples et claires dans la langue demandée, conçues pour être lues à voix haute")
    used_internal_sources: List[str] = Field(default_factory=list, description="Titres ou slugs des fiches internes utilisées")
    used_web_sources: List[SourceItem] = Field(default_factory=list, description="Sources web citées si une recherche internet a été exploitée")


async def search_web(query: str, max_results: int = 4) -> list[dict]:
    """Recherche web en temps réel (Google News RSS Bénin + Wikipédia) sans quota payant ni blocage."""
    results = []
    headers = {"User-Agent": "AgriSmartBenin/1.0 (contact@agriculture.gouv.bj)"}

    # 1. Recherche dans les actualités agricoles du Bénin via Google News RSS
    try:
        search_q = query
        if not any(k in query.lower() for k in ["bénin", "benin", "cotonou", "parakou", "porto-novo"]):
            search_q = f"{query} Bénin agriculture"

        async with httpx.AsyncClient(headers=headers, timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://news.google.com/rss/search",
                params={"q": search_q, "hl": "fr", "gl": "BJ", "ceid": "BJ:fr"}
            )
            if resp.status_code == 200 and resp.text:
                root = ET.fromstring(resp.text)
                items = root.findall(".//item")
                for item in items[:max_results]:
                    t_el = item.find("title")
                    l_el = item.find("link")
                    d_el = item.find("pubDate")
                    title = t_el.text.strip() if t_el is not None and t_el.text else ""
                    link = l_el.text.strip() if l_el is not None and l_el.text else ""
                    date_str = d_el.text.strip() if d_el is not None and d_el.text else ""
                    if title:
                        snippet = f"Actualité récente ({date_str}) sur l'agriculture et les marchés au Bénin."
                        results.append({"title": title, "snippet": snippet, "url": link})
    except Exception as e:
        logger.warning("Recherche actualités web indisponible : %s", e)

    # 2. Si peu de résultats, recherche documentaire sur Wikipédia
    if len(results) < 2:
        try:
            async with httpx.AsyncClient(headers=headers, timeout=6.0, follow_redirects=True) as client:
                resp = await client.get(
                    "https://fr.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "format": "json",
                        "srlimit": 2,
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("query", {}).get("search", []):
                        t = item.get("title", "")
                        raw_snip = item.get("snippet", "")
                        clean_snip = html.unescape(re.sub(r"<[^>]+>", "", raw_snip)).strip()
                        clean_title = t.replace(" ", "_")
                        page_url = f"https://fr.wikipedia.org/wiki/{clean_title}"
                        results.append({"title": f"Encyclopédie : {t}", "snippet": clean_snip, "url": page_url})
        except Exception as e:
            logger.warning("Recherche Wikipédia indisponible : %s", e)

    return results[:max_results]


async def retrieve_database_context(db, user, query: str) -> dict:
    """Récupère le contexte agricole interne de l'utilisateur et de la plateforme."""
    context = {}

    # 1. Fiches pratiques validées
    guides = [g async for g in db["guides"].find({"verified": True})]
    relevant_guides = rank(query, guides)
    if relevant_guides:
        context["fiches_validees"] = [
            {"titre": g["title"], "resume": g["summary"], "etapes": g.get("steps"), "slug": g["slug"]}
            for g in relevant_guides[:3]
        ]

    # 2. Parcelles de l'exploitant
    if user and getattr(user, "role", None) == "farmer":
        lands = [
            {"commune": l.get("commune"), "departement": l.get("department"), "culture": l.get("crop_type"), "surface_ha": l.get("surface_hectares")}
            async for l in db["lands"].find({"npi_owner": user.npi}).limit(4)
        ]
        if lands:
            context["mes_parcelles"] = lands

    # 3. Dernières alertes phytosanitaires récentes
    alerts = [
        {"culture": a.get("crop_identified"), "maladie": a.get("disease_name"), "commune": a.get("commune"), "gravite": a.get("severity")}
        async for a in db["phytosanitary_alerts"].find().sort("created_at", -1).limit(3)
    ]
    if alerts:
        context["alertes_sanitaires_recentes"] = alerts

    # 4. Offres récentes du marché
    market_items = [
        {"culture": o.get("crop_type"), "quantite_kg": o.get("quantity_kg"), "prix_unitaire_fcfa": o.get("price_per_kg_fcfa"), "commune": o.get("commune")}
        async for o in db["market_offers"].find({"status": "active"}).sort("created_at", -1).limit(4)
    ]
    if market_items:
        context["offres_marche_recentes"] = market_items

    return context


async def ask_chatbot(
    db,
    user,
    message: str,
    history: list[dict] | None = None,
    language: str = "fr",
    force_web_search: bool = False,
) -> dict:
    """Orchestre la réponse du chatbot : contexte DB + recherche Web si nécessaire + réponse structurée + audio."""
    history = history or []
    lang_label = LANGUAGES.get(language, "français")

    # 1. Extraction du contexte interne de la base de données
    db_context = await retrieve_database_context(db, user, message)

    # 2. Déterminer si une recherche Web en direct est nécessaire
    need_web = force_web_search or not db_context.get("fiches_validees") or any(
        kw in message.lower() for kw in ["prix", "cours", "actualité", "actu", "météo", "pluie", "loi", "nouvelle", "marché", "exportation", "engrais", "net", "web"]
    )

    web_results = []
    if need_web:
        web_results = await search_web(message, max_results=3)

    # 3. Préparer l'historique et le prompt
    history_formatted = []
    for h in history[-6:]:
        role = "Utilisateur" if h.get("role") == "user" else "Assistant"
        h_content = h.get("content", "")
        history_formatted.append(f"{role}: {h_content}")
    history_str = "\n".join(history_formatted) if history_formatted else "Aucun historique (premier message)"

    system_prompt = (
        "Tu es l'Assistant Agricole Intelligent du Bénin (plateforme officielle Agri Bénin).\n"
        "Tu es un agronome et conseiller bienveillant, clair, concret et pragmatique.\n"
        "Tu aides les exploitants agricoles, acheteurs et conseillers sur les cultures locales (maïs, manioc, ananas, tomate, soja, coton, igname, etc.),\n"
        "la santé des plantes, les engrais, les prix, la météo et la réglementation foncière.\n\n"
        "Règles impératives :\n\n"
        "1. Priorise les données officielles et fiches pratiques validées fournies dans le contexte ci-dessous.\n\n"
        "2. Si des informations web en direct sont fournies (actualités, cours de marché), utilise-les pour enrichir ta réponse et cite clairement la source web.\n\n"
        "3. Ne conseille jamais de pesticides interdits au Bénin ; privilégie les pratiques agroécologiques durables.\n\n"
        f"4. Rédige le champ 'answer' en Markdown clair et aéré. Réponds dans la langue demandée ({lang_label}). "
        "Si la langue demandée est le fon ou le yoruba, rédige des explications simples, naturelles et accessibles aux exploitants.\n\n"
        f"5. Rédige 'audio_summary' en 1 à 2 phrases courtes et simples dans la langue demandée ({lang_label}), spécialement conçues pour la synthèse vocale.\n\n"
        "6. Renseigne dans 'used_internal_sources' les fiches internes réellement utilisées, et dans 'used_web_sources' les sources internet citées."
    )

    prompt = (
        f"{system_prompt}\n\n"
        f"=== CONTEXTE INTERNE DE LA BASE DE DONNÉES ===\n"
        f"{ai_service.to_prompt_json(db_context)}\n\n"
        f"=== RÉSULTATS DE RECHERCHE WEB EN DIRECT ===\n"
        f"{ai_service.to_prompt_json(web_results)}\n\n"
        f"=== HISTORIQUE DE LA CONVERSATION ===\n"
        f"{history_str}\n\n"
        f"=== QUESTION DE L'UTILISATEUR ===\n"
        f"{message}"
    )

    # 4. Appel à Gemini
    out, run_id = await ai_service.generate(
        db,
        purpose="chatbot_conversation",
        schema=ChatbotResponseSchema,
        prompt=prompt,
        requested_by=user.npi if user else None,
        temperature=0.3,
    )

    # 5. Compilation des sources citées
    sources: list[dict] = []
    if db_context.get("fiches_validees"):
        for f in db_context["fiches_validees"]:
            sources.append({
                "source_type": "database",
                "title": f["titre"],
                "url": "/reglementation",
                "snippet": f["resume"],
            })
    for w in out.used_web_sources:
        sources.append({
            "source_type": "web",
            "title": w.title,
            "url": w.url,
            "snippet": w.snippet,
        })
    if not sources and web_results:
        for w in web_results[:2]:
            sources.append({
                "source_type": "web",
                "title": w["title"],
                "url": w["url"],
                "snippet": w["snippet"],
            })

    # 6. Sauvegarde du message dans MongoDB
    doc = {
        "npi": user.npi if user else "anonymous",
        "question": message,
        "language": language,
        "answer": out.answer,
        "audio_summary": out.audio_summary,
        "sources": sources,
        "used_web": len(web_results) > 0,
        "created_at": utcnow(),
        **ai_service.ai_meta(run_id),
    }
    inserted = await db["chatbot_messages"].insert_one(doc)
    doc["_id"] = inserted.inserted_id

    out_dict = serialize_doc(doc)
    msg_id = out_dict["id"]
    out_dict["audio_url"] = f"{settings.API_V1_STR}/chatbot/audio/{msg_id}"
    return out_dict


async def transcribe_voice(db, user, audio_bytes: bytes, mime: str) -> str:
    """Transcrit fidèlement une question vocale (Français, Fon, Yorùbá ou Anglais)."""
    class AudioTranscription(BaseModel):
        transcript: str

    transcript_obj, _ = await ai_service.generate(
        db,
        purpose="chatbot_voice_transcription",
        schema=AudioTranscription,
        parts=[(audio_bytes, mime)],
        requested_by=user.npi if user else None,
        temperature=0.0,
        prompt=(
            "Transcris fidèlement cet enregistrement audio d'un exploitant agricole au Bénin. "
            "Il peut parler en Français, en Fon (fɔngbè) ou en Yorùbá. "
            "Écris fidèlement les paroles entendues."
        ),
    )
    return transcript_obj.transcript.strip()
