import io
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from google import genai
from google.genai import types
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.database import get_database
from app.core.security import CurrentUser, get_current_user
from app.core.utils import utcnow
from app.modules.monitoring.schemas import DiagnosisResponse, DiagnosisResult, HealthStatus, Severity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring & IA Phytosanitaire"])

ai_client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.gemini_enabled else None

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIDE_PX = 1536  # réduit la taille envoyée à l'IA sans perte utile pour le diagnostic

PROMPT_SYSTEME_AGRI = (
    "Tu es un agronome expert en pathologie végétale au Bénin (maïs, manioc, ananas, tomate, etc.). "
    "Analyse l'image fournie et diagnostique les pathologies ou ravageurs en proposant un traitement "
    "biologique ou culturel adapté aux petits exploitants. Si la plante est saine, indique "
    "health_status='Sain', severity='Aucune' et disease_name=null. "
    "Si l'image ne montre pas de plante, indique une confidence_score très faible."
)


def _load_image(image_bytes: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            probe.verify()  # détecte les fichiers corrompus ou falsifiés
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image illisible ou corrompue.")
    image.thumbnail((MAX_IMAGE_SIDE_PX, MAX_IMAGE_SIDE_PX))
    return image


@router.post("/diagnose", response_model=DiagnosisResponse)
async def diagnose_leaf_image(
    crop_hint: str = Form("Maïs", max_length=50),
    file: UploadFile = File(...),
    db=Depends(get_database),
    user: CurrentUser = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Formats acceptés : JPEG, PNG, WebP.",
        )

    image_bytes = await file.read(settings.max_upload_bytes + 1)
    if len(image_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image trop volumineuse (maximum {settings.MAX_UPLOAD_SIZE_MB} Mo).",
        )
    pil_image = _load_image(image_bytes)

    if ai_client is None:
        # Mode simulation : clé API absente. Rien n'est enregistré pour ne pas fausser les statistiques.
        return DiagnosisResponse(
            crop_identified=crop_hint,
            health_status=HealthStatus.ATTAQUE_PARASITAIRE,
            disease_name="Chenille Légionnaire d'Automne (Simulation)",
            severity=Severity.MOYENNE,
            symptoms=["Feuilles perforées", "Présence de déjections"],
            treatment_advice="Appliquer un extrait aqueux de feuilles de Neem.",
            confidence_score=0.0,
            is_simulation=True,
        )

    try:
        # Appel asynchrone : ne bloque pas la boucle d'événements
        response = await ai_client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[f"{PROMPT_SYSTEME_AGRI}\nIndication sur la culture : {crop_hint}.", pil_image],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DiagnosisResult,
                temperature=0.2,
            ),
        )
        result = response.parsed if isinstance(response.parsed, DiagnosisResult) else DiagnosisResult.model_validate_json(response.text)
    except Exception:
        logger.exception("Échec du diagnostic IA")
        # Le détail technique reste dans les logs, pas dans la réponse
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Le service de diagnostic IA est indisponible.")

    insert = await db["phytosanitary_alerts"].insert_one({
        **result.model_dump(mode="json"),
        "farmer_npi": user.npi,
        "crop_hint": crop_hint,
        "original_filename": file.filename,
        "created_at": utcnow(),
    })
    return DiagnosisResponse(**result.model_dump(), alert_id=str(insert.inserted_id))


@router.get("/weather-alerts/{commune}")
async def get_weather_alerts(commune: str):
    # TODO : brancher un vrai service météo (ex. Météo-Bénin, Open-Meteo)
    return {
        "commune": commune,
        "indicator": "Favorable aux semis",
        "rain_probability": "75%",
        "icon_alert": "green",
        "is_simulation": True,
    }
