"""Envoi de SMS. Pour brancher un vrai fournisseur, ajoutez une classe avec la même méthode
`send` et sélectionnez-la dans `get_sms_sender` selon `SMS_PROVIDER`."""
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def mask_phone(phone: str) -> str:
    return f"{phone[:-8]} •• •• {phone[-4:-2]} {phone[-2:]}" if len(phone) > 8 else "••••"


class SimulatedSmsSender:
    name = "simulation"
    exposes_code = True  # le code est renvoyé au frontend pour affichage

    async def send(self, phone: str, text: str) -> None:
        logger.info("[SMS simulé] %s : %s", mask_phone(phone), text)


def get_sms_sender():
    if settings.SMS_PROVIDER == "simulation":
        return SimulatedSmsSender()
    raise RuntimeError(f"Fournisseur SMS inconnu : {settings.SMS_PROVIDER}")
