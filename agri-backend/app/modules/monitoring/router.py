import io
import logging
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from google.genai import types
from PIL import Image, UnidentifiedImageError
from pymongo.errors import DuplicateKeyError

from app.core import ai, geo, tts
from app.core.benin import normalize_commune, normalize_department
from app.core.config import settings
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user
from app.core.utils import CLIENT_REF_DESCRIPTION, CLIENT_REF_PATTERN, as_utc, parse_object_id, serialize_doc, utcnow
from app.modules.lands.service import ensure_owner_or_agent, get_land_or_404
from app.modules.monitoring import weather
from app.modules.monitoring.schemas import (
    LANGUAGES,
    SEVERITY_COLORS,
    DiagnosisResponse,
    DiagnosisResult,
    HealthStatus,
    Severity,
)
from app.modules.notifications.service import notify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring & IA Phytosanitaire"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIDE_PX = 1536  # taille envoyée à l'IA
STORED_IMAGE_SIDE_PX = 800  # taille conservée pour l'historique et le contrôle par les agents
MAX_OFFLINE_AGE = timedelta(days=30)

PROMPT_SYSTEME_AGRI = (
    "Tu es un agronome expert en pathologie végétale au Bénin (maïs, manioc, ananas, tomate, niébé, igname, coton, etc.). "
    "Analyse l'image et diagnostique les maladies ou ravageurs. Tu t'adresses à un petit exploitant qui lit peu : "
    "phrases courtes, mots simples, pas de jargon scientifique. "
    "Privilégie les solutions biologiques et culturales disponibles localement (extrait de neem, piment, cendre, "
    "rotation des cultures, arrachage des plants atteints). Si un produit chimique est vraiment nécessaire, "
    "conseille uniquement un produit homologué au Bénin, acheté chez un distributeur agréé, et recommande de consulter "
    "l'agent de vulgarisation agricole ; ne cite jamais un pesticide interdit. "
    "Si la plante est saine : health_status='Sain', severity='Aucune', disease_name=null. "
    "Si l'image ne montre pas clairement une plante, mets une confidence_score très faible."
)

Language = Literal["fr", "fon", "yo", "en"]


def _load_image(image_bytes: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            probe.verify()  # détecte les fichiers corrompus ou falsifiés
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image illisible ou corrompue.")
    image.thumbnail((MAX_IMAGE_SIDE_PX, MAX_IMAGE_SIDE_PX))
    return image


def _stored_jpeg(image: Image.Image) -> bytes:
    small = image.copy()
    small.thumbnail((STORED_IMAGE_SIDE_PX, STORED_IMAGE_SIDE_PX))
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=70, optimize=True)
    return buf.getvalue()


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _observed_at(captured_at: Optional[datetime]) -> datetime:
    now = utcnow()
    if captured_at is None:
        return now
    captured_at = as_utc(captured_at)
    if captured_at > now + timedelta(minutes=5):
        raise _unprocessable("La date de prise de vue est dans le futur : vérifiez l'heure du téléphone.")
    if captured_at < now - MAX_OFFLINE_AGE:
        raise _unprocessable("Photo trop ancienne (plus de 30 jours) pour la veille sanitaire.")
    return captured_at


async def _resolve_location(db, user, land_id, department, commune, latitude, longitude) -> dict:
    """Localise le diagnostic : indispensable pour la veille sanitaire du territoire."""
    if (latitude is None) != (longitude is None):
        raise _unprocessable("Fournissez la latitude et la longitude ensemble.")
    point = None
    if latitude is not None:
        if not geo.in_benin(longitude, latitude):
            raise _unprocessable("La position GPS est hors du Bénin.")
        point = {"type": "Point", "coordinates": [round(longitude, geo.COORD_DECIMALS), round(latitude, geo.COORD_DECIMALS)]}

    if land_id:
        land = await get_land_or_404(db, land_id)
        if land["npi_owner"] != user.npi:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cette parcelle ne vous appartient pas.")
        return {"land_id": land_id, "department": land["department"], "commune": land["commune"], "location": point or land["centroid"]}

    if not department or not commune:
        raise _unprocessable("Indiquez la parcelle (land_id), ou bien le département et la commune.")
    try:
        loc = {"land_id": None, "department": normalize_department(department).value, "commune": normalize_commune(commune)}
    except ValueError as e:
        raise _unprocessable(str(e))
    loc["location"] = point
    return loc


def _record_out(doc: dict) -> dict:
    out = serialize_doc(doc, id_field="alert_id")
    if doc.get("has_image"):
        out["image_url"] = f"{settings.API_V1_STR}/monitoring/diagnoses/{out['alert_id']}/image"
    return out


async def _check_hotspot(db, doc: dict) -> None:
    """Quand une commune atteint le seuil de cas d'une même maladie, prévient les exploitants et les agents."""
    if doc["health_status"] == HealthStatus.SAIN.value or not doc.get("disease_name"):
        return
    since = utcnow() - timedelta(days=settings.HOTSPOT_WINDOW_DAYS)
    zone = {"department": doc["department"], "commune": doc["commune"], "disease_name": doc["disease_name"]}
    cases = await db["phytosanitary_alerts"].count_documents({**zone, "observed_at": {"$gte": since}})
    if cases != settings.HOTSPOT_MIN_CASES:  # uniquement au franchissement du seuil
        return
    farmers = await db["lands"].distinct("npi_owner", {"department": doc["department"], "commune": doc["commune"]})
    agents = await db["users"].distinct("npi", {"role": {"$in": ["state_agent", "state_supervisor"]}})
    await notify(
        db, farmers + agents, "sanitary_alert", f"Alerte : {doc['disease_name']}",
        f"{cases} cas de {doc['disease_name']} signalés à {doc['commune']} ces {settings.HOTSPOT_WINDOW_DAYS} derniers jours. "
        "Surveillez vos champs et consultez les conseils de traitement.",
        {**zone, "cases": cases},
    )


@router.post("/diagnose", response_model=DiagnosisResponse)
async def diagnose_leaf_image(
    file: UploadFile = File(...),
    crop_hint: str = Form("Maïs", max_length=50),
    land_id: Optional[str] = Form(None, description="Parcelle concernée (fournit automatiquement la localisation)"),
    department: Optional[str] = Form(None),
    commune: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None, ge=-90, le=90),
    longitude: Optional[float] = Form(None, ge=-180, le=180),
    language: Optional[Language] = Form(None, description="Langue du résumé simple ; par défaut la langue du profil"),
    captured_at: Optional[datetime] = Form(None, description="Date de prise de la photo (ISO 8601), pour les envois différés"),
    client_ref: Optional[str] = Form(None, pattern=CLIENT_REF_PATTERN, description=CLIENT_REF_DESCRIPTION),
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    if client_ref:
        existing = await db["phytosanitary_alerts"].find_one({"farmer_npi": user.npi, "client_ref": client_ref})
        if existing:
            return _record_out(existing)  # renvoi hors ligne : pas de second appel à l'IA

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Formats acceptés : JPEG, PNG, WebP.")

    location = await _resolve_location(db, user, land_id, department, commune, latitude, longitude)
    observed_at = _observed_at(captured_at)
    if language is None:
        profile = await db["users"].find_one({"npi": user.npi}, {"preferred_language": 1})
        language = (profile or {}).get("preferred_language", "fr")

    image_bytes = await file.read(settings.max_upload_bytes + 1)
    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Image trop volumineuse (maximum {settings.MAX_UPLOAD_SIZE_MB} Mo).",
        )
    pil_image = _load_image(image_bytes)

    if ai.ai_client is None:
        # Mode simulation : rien n'est enregistré pour ne pas fausser les statistiques
        return DiagnosisResponse(
            crop_identified=crop_hint,
            health_status=HealthStatus.ATTAQUE_PARASITAIRE,
            disease_name="Chenille Légionnaire d'Automne (Simulation)",
            severity=Severity.MOYENNE,
            symptoms=["Feuilles trouées", "Petites crottes dans le cornet"],
            simple_summary="Simulation : une chenille mange les feuilles de votre maïs.",
            treatment_steps=["Piler des feuilles de neem", "Laisser tremper une nuit dans l'eau", "Filtrer", "Pulvériser dans le cornet le soir"],
            treatment_advice="Appliquer un extrait aqueux de feuilles de Neem.",
            confidence_score=0.0,
            alert_color=SEVERITY_COLORS["Moyenne"],
            language=language,
            is_simulation=True,
            observed_at=observed_at,
            **{k: v for k, v in location.items() if v is not None},
        )

    prompt = (
        f"{PROMPT_SYSTEME_AGRI}\nIndication sur la culture : {crop_hint}. Localisation : {location['commune']}, {location['department']}.\n"
        f"Rédige simple_summary en {LANGUAGES[language]} ; tous les autres champs en français."
    )
    try:
        # Appel asynchrone : ne bloque pas la boucle d'événements
        response = await ai.ai_client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[prompt, pil_image],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DiagnosisResult,
                temperature=0.2,
            ),
        )
        result = response.parsed if isinstance(response.parsed, DiagnosisResult) else DiagnosisResult.model_validate_json(response.text)
    except Exception:
        logger.exception("Échec du diagnostic IA")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Le service de diagnostic IA est indisponible.")

    doc = {
        **result.model_dump(mode="json"),
        "alert_color": SEVERITY_COLORS[result.severity.value],
        "farmer_npi": user.npi,
        "crop_hint": crop_hint,
        "language": language,
        "original_filename": file.filename,
        "has_image": True,
        "observed_at": observed_at,
        "created_at": utcnow(),
        # 'location' et 'client_ref' sont omis s'ils sont absents (index 2dsphere et index partiel)
        **{k: v for k, v in {**location, "client_ref": client_ref}.items() if v is not None},
    }
    try:
        res = await db["phytosanitary_alerts"].insert_one(doc)
    except DuplicateKeyError:  # deux envois simultanés du même client_ref
        return _record_out(await db["phytosanitary_alerts"].find_one({"farmer_npi": user.npi, "client_ref": client_ref}))
    doc["_id"] = res.inserted_id
    await db["diagnosis_images"].insert_one({"_id": res.inserted_id, "data": _stored_jpeg(pil_image), "content_type": "image/jpeg"})
    await _check_hotspot(db, doc)
    return _record_out(doc)


@router.get("/diagnoses/me", response_model=list[DiagnosisResponse], summary="Historique de mes diagnostics")
async def my_diagnoses(
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
    land_id: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    filters: dict = {"farmer_npi": user.npi}
    if land_id:
        filters["land_id"] = land_id
    cursor = db["phytosanitary_alerts"].find(filters).sort("observed_at", -1).skip(skip).limit(limit)
    return [_record_out(d) async for d in cursor]


async def _get_diagnosis(db, alert_id: str, user: CurrentUser) -> dict:
    doc = await db["phytosanitary_alerts"].find_one({"_id": parse_object_id(alert_id, "Diagnostic")})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic introuvable.")
    if doc["farmer_npi"] != user.npi and not user.is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé.")
    return doc


@router.get("/diagnoses/{alert_id}", response_model=DiagnosisResponse)
async def get_diagnosis(alert_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    return _record_out(await _get_diagnosis(db, alert_id, user))


@router.get("/diagnoses/{alert_id}/image", response_class=Response, responses={200: {"content": {"image/jpeg": {}}}})
async def get_diagnosis_image(alert_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    doc = await _get_diagnosis(db, alert_id, user)
    image = await db["diagnosis_images"].find_one({"_id": doc["_id"]})
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo indisponible.")
    return Response(content=bytes(image["data"]), media_type=image["content_type"], headers={"Cache-Control": "private, max-age=2592000"})


@router.get("/diagnoses/{alert_id}/audio", response_class=Response, responses=tts.AUDIO_RESPONSES,
            summary="Lecture audio du diagnostic et des étapes de traitement")
async def get_diagnosis_audio(
    alert_id: str,
    format: tts.AudioFormat = "mp3",
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    doc = await _get_diagnosis(db, alert_id, user)
    steps = ". ".join(doc.get("treatment_steps") or [])
    text = f"{doc['simple_summary']}. {'Voici quoi faire : ' + steps if steps else doc['treatment_advice']}"
    return await tts.audio_response(db, text, format, "private, max-age=604800")


# --- Météo ----------------------------------------------------------------------

@router.get("/weather", summary="Prévisions à 7 jours et alerte simple pour une position GPS")
async def get_weather_by_position(latitude: float = Query(..., ge=-90, le=90), longitude: float = Query(..., ge=-180, le=180)):
    if not geo.in_benin(longitude, latitude):
        raise _unprocessable("La position est hors du Bénin.")
    return await weather.forecast(latitude, longitude)


@router.get("/weather-alerts/{commune}", summary="Prévisions et alerte simple pour une commune")
async def get_weather_alerts(commune: str):
    place = await weather.geocode_commune(commune)
    return {"commune": place["name"], "department": place["department"], **await weather.forecast(place["latitude"], place["longitude"])}


@router.get("/weather/land/{land_id}", summary="Prévisions au centre d'une parcelle")
async def get_weather_for_land(land_id: str, db=Depends(get_database), user: CurrentUser = Depends(get_current_user)):
    land = await get_land_or_404(db, land_id)
    ensure_owner_or_agent(land, user)
    lon, lat = land["centroid"]["coordinates"]
    return {"land_id": land_id, "commune": land["commune"], **await weather.forecast(lat, lon)}
