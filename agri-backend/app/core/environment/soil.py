"""Sol : iSDAsoil (30 m, toute l'Afrique), avec incertitude par propriété.

API gratuite (licence CC BY 4.0) : identifiant et mot de passe à créer sur isda-africa.com,
à renseigner dans ISDA_USERNAME / ISDA_PASSWORD.
"""
import asyncio
import time
from statistics import mean

from app.core import external
from app.core.config import settings

SOURCE = "iSDAsoil (iSDA, 30 m)"
DEPTHS = ["0-20", "20-50"]
_token: dict = {"value": None, "expires": 0.0}

# Libellés lisibles des propriétés les plus utiles (les autres sont gardées telles quelles)
LABELS = {
    "ph": "pH",
    "carbon_organic": "Carbone organique",
    "nitrogen_total": "Azote total",
    "phosphorous_extractable": "Phosphore extractible",
    "potassium_extractable": "Potassium extractible",
    "calcium_extractable": "Calcium extractible",
    "magnesium_extractable": "Magnésium extractible",
    "sulphur_extractable": "Soufre extractible",
    "zinc_extractable": "Zinc extractible",
    "cation_exchange_capacity": "Capacité d'échange cationique",
    "clay_content": "Argile",
    "sand_content": "Sable",
    "silt_content": "Limon",
    "stone_content": "Pierrosité",
    "bulk_density": "Densité apparente",
    "bedrock_depth": "Profondeur de la roche",
}


async def _get_token() -> str:
    if _token["value"] and time.monotonic() < _token["expires"]:
        return _token["value"]
    data = await external.request_json("POST", f"{settings.ISDA_BASE_URL}/login",
                                       data={"username": settings.ISDA_USERNAME, "password": settings.ISDA_PASSWORD})
    _token.update(value=data["access_token"], expires=time.monotonic() + 55 * 60)  # jeton valable 60 min
    return _token["value"]


def _parse(payload: dict) -> dict[str, dict]:
    """{"property": {"ph": [{"value": {"value", "unit"}, "uncertainty": [...], "depth": {...}}]}} → valeurs utiles."""
    out = {}
    for prop, entries in (payload.get("property") or {}).items():
        if not entries:
            continue
        e = entries[0]
        value = (e.get("value") or {}).get("value")
        if not isinstance(value, (int, float)):
            continue
        unc = e.get("uncertainty") or []
        band = next((u for u in unc if str(u.get("confidence_interval", "")).startswith("68")), unc[1] if len(unc) > 1 else (unc[0] if unc else None))
        out[prop] = {"value": value, "unit": (e.get("value") or {}).get("unit"),
                     "lower": band.get("lower_bound") if band else None, "upper": band.get("upper_bound") if band else None}
    return out


async def _point(lat: float, lon: float, depth: str) -> dict:
    token = await _get_token()
    payload = await external.cached_json(
        "GET", f"{settings.ISDA_BASE_URL}/isdasoil/v2/soilproperty", ttl_s=30 * 86400,
        params={"lat": round(lat, 5), "lon": round(lon, 5), "depth": depth},
        headers={"Authorization": f"Bearer {token}"},
    )
    return _parse(payload)


def _uncertainty_level(values: list[dict]) -> str | None:
    widths = [(v["upper"] - v["lower"]) / abs(v["value"]) for v in values
              if v.get("upper") is not None and v.get("lower") is not None and v["value"]]
    if not widths:
        return None
    w = mean(widths)
    return "faible" if w < 0.3 else "moyenne" if w < 0.6 else "forte"


async def soil_profile(points: list[tuple[float, float]]) -> dict:
    """Moyenne des propriétés sur quelques points de la parcelle (lat, lon), par profondeur."""
    if not settings.isda_enabled:
        return external.result("non_configure", SOURCE, error="Identifiants iSDAsoil non renseignés (ISDA_USERNAME / ISDA_PASSWORD).")
    try:
        samples = await asyncio.gather(*[_point(lat, lon, d) for lat, lon in points for d in DEPTHS])
    except (external.ExternalUnavailable, KeyError) as e:
        return external.result("indisponible", SOURCE, error=str(e))

    by_depth: dict[str, dict] = {}
    for i, depth in enumerate(DEPTHS):
        rows = samples[i::len(DEPTHS)]
        props = {}
        for prop in {k for r in rows for k in r}:
            vals = [r[prop] for r in rows if prop in r]
            props[prop] = {
                "label": LABELS.get(prop, prop),
                "value": round(mean(v["value"] for v in vals), 3),
                "unit": vals[0]["unit"],
                "uncertainty": _uncertainty_level(vals),
            }
        by_depth[f"{depth} cm"] = props
    return external.result("ok" if any(by_depth.values()) else "indisponible", SOURCE,
                           data={"points_sampled": len(points), "depths": by_depth})


# --- Interprétation indicative (sans IA), pour l'affichage et le mode dégradé -----------------
# Seuils usuels en agronomie tropicale, à faire valider localement (INRAB).
THRESHOLDS = {
    "ph": [(5.5, "acide", "Sol acide : un chaulage peut être utile selon la culture."),
           (7.3, "correct", "pH favorable à la plupart des cultures."),
           (99, "basique", "Sol basique : attention aux carences en oligo-éléments.")],
    "carbon_organic": [(10, "faible", "Peu de matière organique : apports de compost ou de fumier recommandés."),
                       (20, "moyen", "Matière organique moyenne : à entretenir par les résidus de culture."),
                       (9999, "bon", "Bonne teneur en matière organique.")],
    "nitrogen_total": [(1, "faible", "Azote faible : légumineuses en rotation et apports organiques."),
                       (2, "moyen", "Azote moyen."), (9999, "bon", "Azote satisfaisant.")],
    "phosphorous_extractable": [(15, "faible", "Phosphore faible : facteur limitant fréquent."),
                                (30, "moyen", "Phosphore moyen."), (9999, "bon", "Phosphore satisfaisant.")],
    "potassium_extractable": [(80, "faible", "Potassium faible."), (160, "moyen", "Potassium moyen."),
                              (99999, "bon", "Potassium satisfaisant.")],
}


def interpret(profile: dict) -> list[dict]:
    """Lecture simple des valeurs de surface (0-20 cm)."""
    top = ((profile or {}).get("data") or {}).get("depths", {}).get("0-20 cm", {})
    out = []
    for prop, bands in THRESHOLDS.items():
        if prop not in top:
            continue
        v = top[prop]["value"]
        level, comment = next((lvl, c) for limit, lvl, c in bands if v < limit)
        out.append({"parameter": top[prop]["label"], "value": v, "unit": top[prop]["unit"], "level": level,
                    "comment": comment, "uncertainty": top[prop]["uncertainty"]})
    return out
