from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class GuideCategory(str, Enum):
    PRODUITS_INTERDITS = "produits_interdits"
    NORMES_SANITAIRES = "normes_sanitaires"
    REGLEMENTATION = "reglementation"
    BONNES_PRATIQUES = "bonnes_pratiques"
    FAQ = "faq"


CATEGORY_INFO = {
    GuideCategory.PRODUITS_INTERDITS: {"label": "Produits interdits", "pictogram": "forbidden"},
    GuideCategory.NORMES_SANITAIRES: {"label": "Normes sanitaires", "pictogram": "shield"},
    GuideCategory.REGLEMENTATION: {"label": "Lois et démarches", "pictogram": "law"},
    GuideCategory.BONNES_PRATIQUES: {"label": "Bonnes pratiques", "pictogram": "sprout"},
    GuideCategory.FAQ: {"label": "Questions fréquentes", "pictogram": "question"},
}


class GuideBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    category: GuideCategory
    summary: str = Field(..., min_length=10, max_length=500, description="Résumé en mots simples, lu en audio")
    steps: list[str] = Field(default_factory=list, max_length=15, description="Points clés ou étapes, une idée par ligne")
    content: str = Field("", max_length=20_000, description="Texte détaillé (Markdown)")
    pictogram: str = Field("info", max_length=40, description="Code d'icône pour le frontend")
    crops: list[str] = Field(default_factory=list, description="Cultures concernées (vide = toutes)")
    source: str = Field(..., min_length=3, max_length=300, description="Texte officiel ou organisme de référence")
    source_url: Optional[HttpUrl] = None
    verified: bool = Field(False, description="Contenu validé par un agent habilité")


class GuideCreate(GuideBase):
    slug: str = Field(..., pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)


class GuideOut(GuideCreate):
    updated_at: datetime
    updated_by: Optional[str] = None
