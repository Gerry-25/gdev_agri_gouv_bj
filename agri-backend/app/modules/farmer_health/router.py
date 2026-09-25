import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.core import ai_service, tts
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user, require_roles
from app.core.utils import parse_object_id, serialize_doc, utcnow
from app.modules.farmer_health.schemas import (
    HealthAlertCreate,
    HealthAlertOut,
    HealthFacilityItem,
    HealthRecommendation,
    HealthStatsOut,
    HealthStatusUpdate,
    ServiceAssignment,
)
from app.modules.notifications.service import notify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/farmer-health", tags=["Santé des Exploitants"])

# Structures de santé de référence au Bénin
HEALTH_FACILITIES_BENIN = [
    # Ouémé
    {"name": "CHUD Ouémé / Plateau (Porto-Novo)", "department": "Ouémé", "commune": "Porto-Novo", "phone": "+229 20 21 23 88", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Dangbo-Adjohoun-Bonou", "department": "Ouémé", "commune": "Dangbo", "phone": "+229 20 26 01 10", "type": "hopital_de_zone"},
    {"name": "Centre de Santé d'Arrondissement (CSA) Dangbo", "department": "Ouémé", "commune": "Dangbo", "phone": "+229 97 00 11 22", "type": "centre_de_sante"},
    {"name": "Centre de Santé d'Arrondissement (CSA) Adjohoun", "department": "Ouémé", "commune": "Adjohoun", "phone": "+229 97 00 11 23", "type": "centre_de_sante"},
    {"name": "Hôpital de Zone Akpro-Missérété", "department": "Ouémé", "commune": "Akpro-Missérété", "phone": "+229 20 24 50 12", "type": "hopital_de_zone"},
    # Atlantique
    {"name": "CHUD Atlantique (Allada)", "department": "Atlantique", "commune": "Allada", "phone": "+229 21 39 01 44", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Ouidah-Kpomassè-Tori", "department": "Atlantique", "commune": "Ouidah", "phone": "+229 21 34 11 02", "type": "hopital_de_zone"},
    {"name": "Centre de Santé d'Arrondissement (CSA) Allada", "department": "Atlantique", "commune": "Allada", "phone": "+229 97 10 22 33", "type": "centre_de_sante"},
    {"name": "Centre de Santé d'Arrondissement (CSA) Kpomassè", "department": "Atlantique", "commune": "Kpomassè", "phone": "+229 97 10 22 34", "type": "centre_de_sante"},
    # Littoral
    {"name": "CNHU-HKM Cotonou (Urgences & SAMU)", "department": "Littoral", "commune": "Cotonou", "phone": "+229 21 30 01 55", "type": "samu_urgences"},
    {"name": "Hôpital de Zone de Ménontin", "department": "Littoral", "commune": "Cotonou", "phone": "+229 21 38 12 40", "type": "hopital_de_zone"},
    # Zou
    {"name": "CHUD Zou (Abomey)", "department": "Zou", "commune": "Abomey", "phone": "+229 22 50 02 10", "type": "hopital_de_zone"},
    {"name": "Centre de Santé d'Arrondissement (CSA) Bohicon", "department": "Zou", "commune": "Bohicon", "phone": "+229 22 51 03 45", "type": "centre_de_sante"},
    {"name": "Hôpital de Zone Covè-Zagnanado-Ouinhi", "department": "Zou", "commune": "Covè", "phone": "+229 22 53 01 22", "type": "hopital_de_zone"},
    # Borgou
    {"name": "CHUD Borgou (Parakou)", "department": "Borgou", "commune": "Parakou", "phone": "+229 23 61 03 80", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Tchaourou", "department": "Borgou", "commune": "Tchaourou", "phone": "+229 23 63 01 02", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Bembèrèkè", "department": "Borgou", "commune": "Bembèrèkè", "phone": "+229 23 65 00 15", "type": "hopital_de_zone"},
    # Alibori
    {"name": "Hôpital de Zone Kandi", "department": "Alibori", "commune": "Kandi", "phone": "+229 23 63 05 50", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Malanville", "department": "Alibori", "commune": "Malanville", "phone": "+229 23 67 01 10", "type": "hopital_de_zone"},
    {"name": "Centre de Santé d'Arrondissement (CSA) Banikoara", "department": "Alibori", "commune": "Banikoara", "phone": "+229 23 66 01 20", "type": "centre_de_sante"},
    # Mono / Couffo
    {"name": "CHUD Mono (Lokossa)", "department": "Mono", "commune": "Lokossa", "phone": "+229 22 41 12 30", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Comé", "department": "Mono", "commune": "Comé", "phone": "+229 22 43 02 11", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Aplahoué", "department": "Couffo", "commune": "Aplahoué", "phone": "+229 22 46 01 05", "type": "hopital_de_zone"},
    # Atacora / Donga
    {"name": "CHUD Atacora (Natitingou)", "department": "Atacora", "commune": "Natitingou", "phone": "+229 23 82 12 25", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Saint Jean de Dieu (Tanguiéta)", "department": "Atacora", "commune": "Tanguiéta", "phone": "+229 23 83 00 14", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Djougou", "department": "Donga", "commune": "Djougou", "phone": "+229 23 80 02 33", "type": "hopital_de_zone"},
    # Collines / Plateau
    {"name": "Hôpital de Zone Dassa-Zoumè", "department": "Collines", "commune": "Dassa-Zoumè", "phone": "+229 22 55 01 40", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Savalou", "department": "Collines", "commune": "Savalou", "phone": "+229 22 54 02 10", "type": "hopital_de_zone"},
    {"name": "Hôpital de Zone Pobè", "department": "Plateau", "commune": "Pobè", "phone": "+229 20 25 01 15", "type": "hopital_de_zone"},
    {"name": "Centre de Santé d'Arrondissement (CSA) Kétou", "department": "Plateau", "commune": "Kétou", "phone": "+229 20 25 50 12", "type": "centre_de_sante"},
]


def _fallback_health_recommendation(payload: HealthAlertCreate) -> HealthRecommendation:
    """Triage médical et premiers secours d'urgence basés sur les protocoles de santé au travail agricole au Bénin."""
    text = f"{payload.symptoms} {payload.suspected_cause or ''}".lower()

    if any(w in text for w in ["pesticide", "intrant", "chimique", "produit", "épandage", "pulvéris", "herbicid", "insectic"]):
        is_severe = any(w in text for w in ["vomiss", "convuls", "respir", "inconscien", "somnol", "vue", "étourdi"])
        return HealthRecommendation(
            urgency_level="vitale" if is_severe else "urgente",
            urgency_label="Urgence vitale - Intoxication chimique aiguë" if is_severe else "Urgence médicale - Exposition aux pesticides",
            category="intoxication_pesticide",
            category_label="Intoxication aux produits phytosanitaires / pesticides",
            first_aid_steps=[
                "Éloigner immédiatement la victime de la zone traitée et retirer tous les vêtements contaminés avec précaution.",
                "Laver abondamment à grande eau claire et savon la peau, les cheveux et les yeux pendant au moins 15 minutes.",
                "Maintenir la victime au calme et en position latérale de sécurité si elle respire mais somnole.",
                "Conserver impérativement l'emballage, l'étiquette ou le nom précis du produit pour l'équipe soignante.",
            ],
            things_to_avoid=[
                "NE PAS faire vomir (risque majeur d'asphyxie et de brûlures caustiques de l'œsophage et des poumons).",
                "NE PAS donner de lait, d'huile, ni d'alcool (ils facilitent l'absorption intestinale des toxiques).",
                "NE PAS laisser la victime seule un seul instant.",
            ],
            medical_orientation=f"Évacuation immédiate vers le Centre de Santé ou Hôpital de Zone de {payload.commune} ({payload.department}).",
            simple_summary="Suspicion d'intoxication aux pesticides. Lavez abondamment la peau à l'eau courante et retirez les habits souillés. Ne faites surtout pas vomir et rendez-vous sans attendre au centre de santé avec l'emballage du produit.",
        )

    if any(w in text for w in ["serpent", "morsure", "crochet", "venin", "scorpion", "piqûre"]):
        return HealthRecommendation(
            urgency_level="vitale",
            urgency_label="Urgence vitale - Envenimation suspectée",
            category="morsure_piqure",
            category_label="Morsure de serpent ou envenimation animale",
            first_aid_steps=[
                "Allonger immédiatement la victime au repos complet (l'agitation accélère la diffusion sanguine du venin).",
                "Immobiliser le membre atteint avec une attelle ou une écharpe, en position basse sous le niveau du cœur.",
                "Retirer tout de suite bagues, bracelets et vêtements serrés avant l'installation du gonflement (œdème).",
                "Nettoyer doucement à l'eau claire sans frotter et organiser le transport d'urgence.",
            ],
            things_to_avoid=[
                "NE JAMAIS poser de garrot serré (risque de gangrène et de nécrose du membre).",
                "NE JAMAIS inciser, taillader, brûler ou sucer la plaie au niveau des morsures.",
                "NE PAS appliquer de poudres traditionnelles, terre ou glace sur la plaie.",
            ],
            medical_orientation=f"Transfert d'urgence absolu vers l'Hôpital de Zone de référence ({payload.department}) disposant de sérum antivenimeux.",
            simple_summary="Morsure de serpent suspectée : gardez la victime allongée et parfaitement calme sans bouger le membre mordu. Ne posez aucun garrot et n'incisez pas. Rejoignez immédiatement l'hôpital pour injection du sérum.",
        )

    if any(w in text for w in ["machette", "coupe", "bless", "saign", "plaie", "chute", "fractur", "outil"]):
        is_bleeding = any(w in text for w in ["saign", "hémorragie", "profond"])
        return HealthRecommendation(
            urgency_level="urgente" if is_bleeding else "moderee",
            urgency_label="Urgence traumatique - Plaie ou blessure agricole",
            category="traumatisme_agricole",
            category_label="Traumatisme et accident d'outil agricole",
            first_aid_steps=[
                "Comprimer fermement la plaie avec un tissu ou linge très propre pour stopper le saignement.",
                "Surélever le membre blessé par rapport au cœur si le saignement persiste.",
                "Nettoyer à l'eau claire et au savon neutre si la plaie est superficielle.",
                "Vérifier le statut vaccinal contre le tétanos au centre médical.",
            ],
            things_to_avoid=[
                "NE PAS retirer un corps étranger (morceau de métal, bois) profondément fiché dans la plaie.",
                "NE PAS mettre de terre, café, cendre ou feuilles pilées sur la plaie vive (risque de tétanos mortel).",
            ],
            medical_orientation=f"Consultation au Centre de Santé d'Arrondissement de {payload.commune} pour suture, pansement stérile et vaccin antitétanique.",
            simple_summary="Blessure de travail agricole : comprimez la plaie avec un linge propre pour arrêter le saignement. Ne mettez pas de terre ni de poudre sur la plaie et consultez pour prévenir le tétanos.",
        )

    if any(w in text for w in ["soleil", "chaleur", "insol", "déshydrat", "soif", "vertig", "évanoui", "malaise"]):
        return HealthRecommendation(
            urgency_level="moderee" if payload.urgency_perceived != "vitale" else "urgente",
            urgency_label="Coup de chaleur et déshydratation aiguë",
            category="coup_chaleur_deshydratation",
            category_label="Coup de chaleur et surmenage thermique",
            first_aid_steps=[
                "Placer la personne immédiatement à l'ombre dans un endroit aéré et frais.",
                "Desserrer ou retirer les vêtements lourds.",
                "Faire boire de l'eau fraîche par petites gorgées progressives.",
                "Humidifier le front, le cou et le thorax avec un tissu ou de l'eau tiède.",
            ],
            things_to_avoid=[
                "NE PAS faire boire une personne inconsciente ou somnolente.",
                "NE PAS plonger brusquement la victime dans de l'eau glacée (choc thermique).",
            ],
            medical_orientation=f"Centre de santé le plus proche de {payload.commune} si les vertiges ou la confusion persistent après 30 minutes de repos.",
            simple_summary="Coup de chaleur : installez la personne à l'ombre, desserrez les vêtements et donnez-lui à boire de l'eau fraîche petit à petit. Consultez si l'état ne s'améliore pas rapidement.",
        )

    if any(w in text for w in ["fièvre", "palu", "frisson", "courbatur", "céphalée", "maux de tête"]):
        return HealthRecommendation(
            urgency_level="moderee",
            urgency_label="Syndrome fébrile - Suspicion de paludisme ou infection",
            category="infectieux_paludisme",
            category_label="Maladie fébrile ou infectieuse",
            first_aid_steps=[
                "Repos complet sous moustiquaire imprégnée d'insecticide.",
                "Boire beaucoup d'eau potable et bouillie pour compenser la transpiration.",
                "Prendre du paracétamol selon la posologie pour soulager la fièvre et les douleurs.",
            ],
            things_to_avoid=[
                "NE PAS prendre d'anti-inflammatoires (ibuprofène, aspirine) sans test de diagnostic rapide (TDR).",
                "NE PAS pratiquer d'automédication avec des antibiotiques sans prescription.",
            ],
            medical_orientation=f"Centre de Santé d'Arrondissement de {payload.commune} pour réalisation d'un TDR Paludisme et prise en charge adaptée.",
            simple_summary="Fièvre et suspicion de paludisme : reposez-vous, hydratez-vous bien et faites réaliser un test rapide (TDR) au centre de santé le plus proche afin de recevoir le traitement officiel.",
        )

    return HealthRecommendation(
        urgency_level=payload.urgency_perceived,
        urgency_label=f"Problème de santé signalé ({payload.urgency_perceived})",
        category="autre",
        category_label="Autre problème de santé",
        first_aid_steps=[
            "Mettre la personne au repos dans un cadre sécurisé et calme.",
            "Surveiller régulièrement l'état général, la respiration et la lucidité.",
            "Noter l'heure d'apparition des symptômes pour informer le personnel soignant.",
        ],
        things_to_avoid=[
            "NE PAS prendre de médicaments forts sans avis médical d'un professionnel de santé.",
        ],
        medical_orientation=f"Présentez-vous au centre de santé d'arrondissement de {payload.commune} pour examen clinique.",
        simple_summary="Votre signalement a bien été enregistré. Suivez les consignes de repos et rapprochez-vous du centre de santé de votre secteur.",
    )


async def _analyze_health_with_ai(db, payload: HealthAlertCreate, npi: str) -> HealthRecommendation:
    """Analyse les symptômes avec Gemini ou bascule sur le triage médical agronomique d'urgence."""
    prompt = (
        "Tu es un médecin spécialiste de la santé des exploitants agricoles et de la médecine du travail au Bénin.\n"
        "Un exploitant agricole ou l'un de ses proches signale un problème de santé survenu au champ ou dans sa communauté.\n"
        "Analyse la situation avec bienveillance, rigueur et réactivité :\n\n"
        f"- Symptômes : {payload.symptoms}\n"
        f"- Cause suspectée : {payload.suspected_cause or 'Non précisée'}\n"
        f"- Lien avec le travail agricole : {'Oui' if payload.work_related else 'Non'}\n"
        f"- Patient concerné : {payload.patient_relation} ({payload.patient_name or 'Exploitant'})\n"
        f"- Localisation : {payload.commune}, département de {payload.department}\n"
        f"- Urgence ressentie par le déclarant : {payload.urgency_perceived}\n\n"
        "Consignes impératives :\n"
        "1. Identifie la catégorie (intoxication_pesticide, traumatisme_agricole, morsure_piqure, coup_chaleur_deshydratation, infectieux_paludisme, ou autre).\n"
        "2. Évalue l'urgence réelle : 'vitale' (mise en jeu du pronostic vital, asphyxie, choc, coma, morsure grave), 'urgente', 'moderee', 'faible'.\n"
        "3. Donne 3 à 4 gestes de premiers secours immédiats, concrets et réalisables en milieu rural.\n"
        "4. Indique 2 à 3 choses à ABSOLUMENT ÉVITER (contre-indications vitales).\n"
        "5. Oriente clairement vers le type de structure médicale adaptée au Bénin (CSA, Hôpital de Zone, SAMU).\n"
        "6. Rédige un résumé simple de 2-3 phrases faciles à comprendre."
    )

    try:
        recommendation, _ = await ai_service.generate(
            db,
            purpose="farmer_health_advice",
            schema=HealthRecommendation,
            prompt=prompt,
            requested_by=npi,
            temperature=0.2,
        )
        return recommendation
    except Exception as exc:
        logger.warning("IA indisponible pour le diagnostic santé (%s), utilisation du triage expert de secours", exc)
        return _fallback_health_recommendation(payload)


@router.post("/alerts", status_code=status.HTTP_201_CREATED, response_model=HealthAlertOut, summary="Signaler un problème de santé d'un exploitant")
async def create_health_alert(
    payload: HealthAlertCreate,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    """L'exploitant déclare un problème de santé. L'IA génère les recommandations et les agents sont notifiés."""
    patient_name = payload.patient_name or user.full_name or "Exploitant"

    # 1. Analyse médicale et premiers secours par IA (avec fallback fiable)
    recommendation = await _analyze_health_with_ai(db, payload, user.npi)

    now = utcnow()
    doc: dict[str, Any] = {
        "npi": user.npi,
        "patient_name": patient_name,
        "patient_relation": payload.patient_relation,
        "phone": payload.phone,
        "department": payload.department,
        "commune": payload.commune,
        "locality": payload.locality,
        "land_id": payload.land_id,
        "symptoms": payload.symptoms,
        "suspected_cause": payload.suspected_cause,
        "work_related": payload.work_related,
        "urgency_perceived": payload.urgency_perceived,
        "urgency_level": recommendation.urgency_level,
        "urgency_label": recommendation.urgency_label,
        "category": recommendation.category,
        "category_label": recommendation.category_label,
        "ai_recommendation": recommendation.model_dump(mode="json"),
        "status": "signale",
        "assigned_service": None,
        "resolution_notes": None,
        "created_at": now,
        "updated_at": now,
    }

    res = await db["farmer_health_alerts"].insert_one(doc)
    doc["_id"] = res.inserted_id

    # 2. Notifier les agents territoriaux si urgence vitale ou élevée
    if recommendation.urgency_level in ("vitale", "urgente"):
        agents_cursor = db["users"].find({"role": {"$in": ["state_agent", "state_supervisor"]}}, {"npi": 1})
        agent_npis = [a["npi"] async for a in agents_cursor]
        await notify(
            db,
            agent_npis,
            type_="health_alert",
            title=f"Alerte Santé : {recommendation.urgency_label}",
            message=f"{patient_name} à {payload.commune} ({payload.department}) : {recommendation.category_label}.",
            data={"alert_id": str(res.inserted_id), "urgency": recommendation.urgency_level, "commune": payload.commune},
        )

    return serialize_doc(doc)


@router.get("/alerts/me", response_model=list[HealthAlertOut], summary="Mes alertes de santé (exploitant)")
async def get_my_health_alerts(
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    """Historique des alertes de santé soumises par l'exploitant connecté."""
    cursor = db["farmer_health_alerts"].find({"npi": user.npi}).sort("created_at", -1)
    return [serialize_doc(doc) async for doc in cursor]


@router.get("/alerts/{alert_id}", response_model=HealthAlertOut, summary="Détail d'une alerte de santé")
async def get_health_alert_detail(
    alert_id: str,
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    """Consulter une alerte spécifique (exploitant auteur ou agent de l'État)."""
    oid = parse_object_id(alert_id, "Alerte de santé")
    doc = await db["farmer_health_alerts"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerte de santé introuvable.")

    is_agent = user.role in ("state_agent", "state_supervisor")
    if doc["npi"] != user.npi and not is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès non autorisé à cette fiche médicale.")

    return serialize_doc(doc)


@router.get("/alerts/{alert_id}/audio", response_class=Response, responses=tts.AUDIO_RESPONSES, summary="Lecture audio des recommandations santé")
async def get_alert_audio(
    alert_id: str,
    format: tts.AudioFormat = "mp3",
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    """Génère la lecture audio des consignes de premiers secours et résumé santé pour l'exploitant."""
    oid = parse_object_id(alert_id, "Alerte de santé")
    doc = await db["farmer_health_alerts"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerte de santé introuvable.")

    is_agent = user.role in ("state_agent", "state_supervisor")
    if doc["npi"] != user.npi and not is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès non autorisé.")

    rec = doc.get("ai_recommendation") or {}
    summary = rec.get("simple_summary") or ""
    steps = ". ".join(rec.get("first_aid_steps") or [])
    avoid = ". ".join(rec.get("things_to_avoid") or rec.get("avoid") or [])

    parts = []
    if summary:
        parts.append(summary)
    if steps:
        parts.append(f"Premiers secours : {steps}")
    if avoid:
        parts.append(f"À éviter absolument : {avoid}")

    text_to_speak = " ".join(parts) or "Aucune consigne disponible pour le moment."
    return await tts.audio_response(db, text_to_speak, format, "public, max-age=604800", language="fr")


@router.get("/alerts", response_model=list[HealthAlertOut], summary="Vue globale des alertes de santé (agents)")
async def list_health_alerts(
    status_filter: Optional[str] = Query(None, alias="status", description="Filtrer par statut (signale, pris_en_charge, en_cours, resolu)"),
    urgency_filter: Optional[str] = Query(None, alias="urgency", description="Filtrer par urgence (vitale, urgente, moderee, faible)"),
    category_filter: Optional[str] = Query(None, alias="category", description="Filtrer par catégorie"),
    department: Optional[str] = Query(None, description="Filtrer par département"),
    commune: Optional[str] = Query(None, description="Filtrer par commune"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    """Vue cockpit globale des alertes de santé pour les agents et superviseurs."""
    filters: dict[str, Any] = {}
    if status_filter:
        filters["status"] = status_filter
    if urgency_filter:
        filters["urgency_level"] = urgency_filter
    if category_filter:
        filters["category"] = category_filter
    if department:
        filters["department"] = department
    if commune:
        filters["commune"] = commune

    cursor = db["farmer_health_alerts"].find(filters).sort("created_at", -1).skip(skip).limit(limit)
    return [serialize_doc(doc) async for doc in cursor]


@router.get("/stats", response_model=HealthStatsOut, summary="Statistiques globales de santé (agents)")
async def get_health_stats(
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    """Agrégation des alertes sanitaires des exploitants pour la prise de décision."""
    total = await db["farmer_health_alerts"].count_documents({})
    pending = await db["farmer_health_alerts"].count_documents({"status": "signale"})
    in_treatment = await db["farmer_health_alerts"].count_documents({"status": {"$in": ["pris_en_charge", "en_cours"]}})
    resolved = await db["farmer_health_alerts"].count_documents({"status": "resolu"})
    vital = await db["farmer_health_alerts"].count_documents({"urgency_level": "vitale", "status": {"$ne": "resolu"}})

    # Répartition par urgence
    urgency_agg = await db["farmer_health_alerts"].aggregate([
        {"$group": {"_id": "$urgency_level", "count": {"$sum": 1}}},
    ]).to_list(10)
    by_urgency = {item["_id"]: item["count"] for item in urgency_agg if item["_id"]}

    # Répartition par catégorie
    category_agg = await db["farmer_health_alerts"].aggregate([
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
    ]).to_list(10)
    by_category = {item["_id"]: item["count"] for item in category_agg if item["_id"]}

    # Répartition par département
    dept_agg = await db["farmer_health_alerts"].aggregate([
        {"$group": {"_id": "$department", "count": {"$sum": 1}}},
    ]).to_list(20)
    by_department = {item["_id"]: item["count"] for item in dept_agg if item["_id"]}

    # Détection de foyers/clusters sanitaires (communes avec >= 2 alertes actives)
    hotspots_agg = await db["farmer_health_alerts"].aggregate([
        {"$match": {"status": {"$ne": "resolu"}}},
        {"$group": {"_id": {"department": "$department", "commune": "$commune"}, "count": {"$sum": 1}}},
        {"$match": {"count": {"$gte": 2}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]).to_list(10)
    recent_hotspots = [
        {"department": h["_id"]["department"], "commune": h["_id"]["commune"], "active_cases": h["count"]}
        for h in hotspots_agg
    ]

    return HealthStatsOut(
        total_alerts=total,
        pending_alerts=pending,
        in_treatment_alerts=in_treatment,
        resolved_alerts=resolved,
        vital_urgencies=vital,
        by_urgency=by_urgency,
        by_category=by_category,
        by_department=by_department,
        recent_hotspots=recent_hotspots,
    )


@router.patch("/alerts/{alert_id}/assign", response_model=HealthAlertOut, summary="Assigner un service de santé à une alerte")
async def assign_health_service(
    alert_id: str,
    payload: ServiceAssignment,
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    """Un agent affecte un centre ou une équipe médicale pour secourir ou soigner l'exploitant."""
    oid = parse_object_id(alert_id, "Alerte de santé")
    doc = await db["farmer_health_alerts"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerte de santé introuvable.")

    now = utcnow()
    assignment_doc = {
        **payload.model_dump(mode="json"),
        "assigned_by": agent.npi,
        "assigned_at": now,
    }

    await db["farmer_health_alerts"].update_one(
        {"_id": oid},
        {"$set": {
            "assigned_service": assignment_doc,
            "status": "pris_en_charge",
            "updated_at": now,
        }},
    )

    # Notifier l'exploitant
    await notify(
        db,
        [doc["npi"]],
        type_="health_assigned",
        title="Service de santé assigné",
        message=f"Votre alerte santé a été confiée à : {payload.facility_name}. {payload.instructions or ''}",
        data={"alert_id": alert_id, "facility": payload.facility_name},
    )

    updated = await db["farmer_health_alerts"].find_one({"_id": oid})
    return serialize_doc(updated)


@router.patch("/alerts/{alert_id}/status", response_model=HealthAlertOut, summary="Mettre à jour le statut de prise en charge")
async def update_health_status(
    alert_id: str,
    payload: HealthStatusUpdate,
    db=Depends(get_database),
    agent: CurrentUser = Depends(require_roles("state_agent", "state_supervisor")),
):
    """Mettre à jour l'évolution médicale (en cours de traitement, résolu, etc.)."""
    oid = parse_object_id(alert_id, "Alerte de santé")
    doc = await db["farmer_health_alerts"].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerte de santé introuvable.")

    now = utcnow()
    update_data: dict[str, Any] = {
        "status": payload.status,
        "updated_at": now,
    }
    if payload.notes:
        update_data["resolution_notes"] = payload.notes

    await db["farmer_health_alerts"].update_one({"_id": oid}, {"$set": update_data})

    # Notifier l'exploitant si l'alerte est marquée comme résolue
    if payload.status == "resolu":
        await notify(
            db,
            [doc["npi"]],
            type_="health_updated",
            title="Dossier santé clôturé",
            message=f"Votre signalement médical a été marqué comme résolu. {payload.notes or ''}",
            data={"alert_id": alert_id, "status": "resolu"},
        )

    updated = await db["farmer_health_alerts"].find_one({"_id": oid})
    return serialize_doc(updated)


@router.get("/facilities", response_model=list[HealthFacilityItem], summary="Centres de santé de référence au Bénin")
async def list_health_facilities(
    department: Optional[str] = Query(None, description="Filtrer par département"),
    commune: Optional[str] = Query(None, description="Filtrer par commune"),
    _: CurrentUser = Depends(get_current_user),
):
    """Liste des centres de santé et hôpitaux de référence au Bénin."""
    res = HEALTH_FACILITIES_BENIN
    if department:
        res = [f for f in res if f["department"].lower() == department.lower()]
    if commune:
        res = [f for f in res if f["commune"].lower() == commune.lower()]
    return res
