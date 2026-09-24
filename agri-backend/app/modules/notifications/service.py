"""Notifications dans l'application (consultées par le frontend)."""
from app.core.utils import utcnow

PICTOGRAMS = {
    "dispute_opened": "law",
    "dispute_updated": "law",
    "transfer_requested": "handshake",
    "transfer_updated": "handshake",
    "land_verified": "check",
    "offer_interest": "buyer",
    "sanitary_alert": "bug",
}


async def notify(db, npis, type_: str, title: str, message: str, data: dict | None = None) -> int:
    recipients = sorted({n for n in npis if n and n != "systeme"})
    if not recipients:
        return 0
    now = utcnow()
    await db["notifications"].insert_many([
        {"npi": npi, "type": type_, "title": title, "message": message, "data": data or {},
         "pictogram": PICTOGRAMS.get(type_, "info"), "read": False, "created_at": now}
        for npi in recipients
    ])
    return len(recipients)
