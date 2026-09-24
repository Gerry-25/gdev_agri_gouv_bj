from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Les dates relues sans fuseau (selon la configuration Mongo) sont considérées en UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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


CLIENT_REF_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"
CLIENT_REF_DESCRIPTION = (
    "Identifiant unique généré par l'application (ex. UUID). Un envoi rejoué avec le même "
    "client_ref (file d'attente hors ligne) renvoie la ressource existante au lieu d'un doublon."
)
