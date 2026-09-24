from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valeurs considérées comme "non configurées" pour la clé Gemini
_PLACEHOLDERS = {"", "VOTRE_CLE_GEMINI_ICI", "changeme", "your_api_key"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: Literal["development", "demo", "production"] = "development"
    PROJECT_NAME: str = "AgriSmart Benin API"
    API_V1_STR: str = "/api/v1"

    # Obligatoires : aucune valeur par défaut contenant des identifiants
    MONGODB_URL: str
    DATABASE_NAME: str = "agri_smart_db"

    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, gt=0)

    # Code de connexion par SMS. "simulation" : le code est renvoyé dans la réponse
    # pour être affiché par le frontend, en attendant un vrai fournisseur SMS.
    SMS_PROVIDER: Literal["simulation"] = "simulation"
    OTP_LENGTH: int = Field(default=6, ge=4, le=8)
    OTP_TTL_SECONDS: int = Field(default=300, gt=0)
    OTP_RESEND_SECONDS: int = Field(default=60, ge=0)
    OTP_MAX_PER_HOUR: int = Field(default=5, gt=0)
    OTP_MAX_ATTEMPTS: int = Field(default=5, gt=0)

    # IA
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_TTS_MODEL: str = "gemini-2.5-flash-preview-tts"
    TTS_VOICE: str = "Kore"
    TTS_MAX_CHARS: int = Field(default=1200, gt=0)

    # Météo (Open-Meteo : gratuit, sans clé)
    OPEN_METEO_FORECAST_URL: str = "https://api.open-meteo.com/v1/forecast"
    OPEN_METEO_GEOCODING_URL: str = "https://geocoding-api.open-meteo.com/v1/search"
    WEATHER_CACHE_MINUTES: int = Field(default=30, gt=0)

    # Parcelles
    LAND_MIN_AREA_M2: float = Field(default=50, gt=0)
    LAND_MAX_AREA_HA: float = Field(default=10_000, gt=0)
    LAND_MAX_POINTS: int = Field(default=1000, ge=3)
    # Chevauchement toléré (imprécision GPS des téléphones, bordures partagées)
    LAND_OVERLAP_TOLERANCE_M2: float = Field(default=25, ge=0)

    # Veille sanitaire : nombre de cas pour qualifier un foyer
    HOTSPOT_MIN_CASES: int = Field(default=3, ge=1)
    HOTSPOT_WINDOW_DAYS: int = Field(default=30, ge=1)

    # Score de performance des exploitants
    PERFORMANCE_MIN_SEASONS: int = Field(default=2, ge=1, description="Saisons de récolte vérifiées requises pour être éligible")

    # Appels à candidatures sur le domaine privé de l'État (durées à ajuster selon les textes en vigueur)
    CALL_MIN_OPEN_DAYS: int = Field(default=15, ge=1, description="Durée minimale de publicité d'un appel")
    CALL_CONTEST_DAYS: int = Field(default=15, ge=0, description="Délai de contestation après validation de l'attribution")
    AWARD_ACCEPTANCE_DAYS: int = Field(default=15, ge=1, description="Délai laissé au lauréat pour accepter")
    MAX_ACTIVE_CONCESSIONS_PER_FARMER: int = Field(default=1, ge=1)

    CORS_ORIGINS: str = "http://localhost:3000"
    MAX_UPLOAD_SIZE_MB: int = Field(default=5, gt=0, le=20)
    STATE_REVENUE_RATE: float = Field(default=0.015, ge=0, le=1)

    @field_validator("GEMINI_API_KEY")
    @classmethod
    def _ignore_placeholder_key(cls, v: str) -> str:
        v = v.strip()
        return "" if v in _PLACEHOLDERS else v

    @model_validator(mode="after")
    def _no_simulation_in_production(self):
        if self.APP_ENV == "production" and self.SMS_PROVIDER == "simulation":
            raise ValueError("SMS_PROVIDER=simulation est interdit quand APP_ENV=production : branchez un vrai fournisseur SMS.")
        return self

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


settings = Settings()
