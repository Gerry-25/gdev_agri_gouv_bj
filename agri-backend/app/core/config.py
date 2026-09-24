from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valeurs considérées comme "non configurées" pour la clé Gemini
_PLACEHOLDERS = {"", "VOTRE_CLE_GEMINI_ICI", "changeme", "your_api_key"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "AgriSmart Benin API"
    API_V1_STR: str = "/api/v1"

    # Obligatoires : aucune valeur par défaut contenant des identifiants
    MONGODB_URL: str
    DATABASE_NAME: str = "agri_smart_db"

    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, gt=0)

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    CORS_ORIGINS: str = "http://localhost:3000"
    MAX_UPLOAD_SIZE_MB: int = Field(default=5, gt=0, le=20)
    STATE_REVENUE_RATE: float = Field(default=0.015, ge=0, le=1)

    @field_validator("GEMINI_API_KEY")
    @classmethod
    def _ignore_placeholder_key(cls, v: str) -> str:
        v = v.strip()
        return "" if v in _PLACEHOLDERS else v

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
