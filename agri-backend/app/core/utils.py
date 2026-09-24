from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serialize_doc(doc: dict) -> dict:
    """Convertit l'_id MongoDB en champ 'id' lisible par le client."""
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc
