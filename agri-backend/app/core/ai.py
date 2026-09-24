"""Client Gemini partagé (None si aucune clé n'est configurée)."""
from google import genai

from app.core.config import settings

ai_client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.gemini_enabled else None
