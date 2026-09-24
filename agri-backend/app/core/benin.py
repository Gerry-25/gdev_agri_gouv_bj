"""Référentiels et normalisations propres au Bénin."""
import re
import unicodedata
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator


class Department(str, Enum):
    ALIBORI = "Alibori"
    ATACORA = "Atacora"
    ATLANTIQUE = "Atlantique"
    BORGOU = "Borgou"
    COLLINES = "Collines"
    COUFFO = "Couffo"
    DONGA = "Donga"
    LITTORAL = "Littoral"
    MONO = "Mono"
    OUEME = "Ouémé"
    PLATEAU = "Plateau"
    ZOU = "Zou"


def _key(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().strip().lower()


_DEPARTMENTS = {_key(d.value): d for d in Department}


def normalize_department(v) -> Department:
    """Accepte 'oueme', 'OUÉMÉ', 'Ouémé'… et renvoie la valeur officielle."""
    if isinstance(v, Department):
        return v
    if isinstance(v, str) and _key(v) in _DEPARTMENTS:
        return _DEPARTMENTS[_key(v)]
    raise ValueError(f"Département inconnu. Valeurs possibles : {', '.join(d.value for d in Department)}")


def normalize_commune(v: str) -> str:
    v = " ".join(str(v).split())
    if not 2 <= len(v) <= 60:
        raise ValueError("Nom de commune invalide.")
    return v.title()


def normalize_phone(v: str) -> str:
    """Normalise au format international +229 01XXXXXXXX.

    Les anciens numéros à 8 chiffres reçoivent le préfixe 01 (numérotation béninoise à 10 chiffres).
    """
    digits = re.sub(r"\D", "", str(v))
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 8:
        digits = "22901" + digits
    elif len(digits) == 10 and digits.startswith("01"):
        digits = "229" + digits
    if not 11 <= len(digits) <= 15:
        raise ValueError("Numéro de téléphone invalide.")
    return "+" + digits


DepartmentField = Annotated[Department, BeforeValidator(normalize_department)]
CommuneField = Annotated[str, AfterValidator(normalize_commune)]
PhoneField = Annotated[str, AfterValidator(normalize_phone)]
