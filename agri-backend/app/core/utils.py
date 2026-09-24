from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize_doc(doc: dict, id_field: str = "id") -> dict:
    """Convertit l'_id MongoDB en champ 'id' lisible par le client."""
    doc = dict(doc)
    doc[id_field] = str(doc.pop("_id"))
    return doc


def parse_object_id(value: str, label: str = "Ressource") -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} introuvable.")
