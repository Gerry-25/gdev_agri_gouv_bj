"""Météo réelle via Open-Meteo (gratuit, sans clé) et indicateurs simples vert/orange/rouge."""
import logging
import time

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_DAILY_VARS = "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,weather_code"
_cache: dict[str, tuple[float, dict]] = {}


async def _get_json(url: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


async def _cached(key: str, ttl_s: float, url: str, params: dict) -> dict:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl_s:
        return hit[1]
    try:
        data = await _get_json(url, params)
    except (httpx.HTTPError, ValueError):
        logger.exception("Échec de l'appel météo")
        if hit:  # mieux vaut une prévision un peu ancienne que rien
            return hit[1]
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service météo momentanément indisponible.")
    _cache[key] = (time.monotonic(), data)
    return data


async def geocode_commune(commune: str) -> dict:
    data = await _cached(
        f"geo:{commune.lower()}", 30 * 24 * 3600, settings.OPEN_METEO_GEOCODING_URL,
        {"name": commune, "count": 10, "language": "fr", "countryCode": "BJ", "format": "json"},
    )
    results = [r for r in data.get("results") or [] if r.get("country_code") == "BJ"]
    if not results:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Commune « {commune} » introuvable au Bénin.")
    r = results[0]
    return {"name": r["name"], "department": r.get("admin1"), "latitude": r["latitude"], "longitude": r["longitude"]}


def _day_assessment(d: dict) -> tuple[str, str]:
    rain, wind, tmax = d["precipitation_mm"], d["wind_kmh"], d["tmax"]
    if rain >= 50:
        return "red", "rain_heavy"
    if wind >= 50:
        return "red", "wind"
    if tmax >= 40:
        return "red", "heat"
    if rain >= 30:
        return "orange", "rain_heavy"
    if tmax >= 36:
        return "orange", "heat"
    if wind >= 35:
        return "orange", "wind"
    if rain >= 2 or d["precipitation_probability"] >= 50:
        return "green", "rain"
    return "green", "sun"


def evaluate(daily: dict) -> tuple[list[dict], dict]:
    def col(name):
        return daily.get(name) or [None] * len(daily.get("time", []))

    days = []
    for i, day in enumerate(daily.get("time", [])):
        d = {
            "date": day,
            "tmin": col("temperature_2m_min")[i],
            "tmax": col("temperature_2m_max")[i] or 0,
            "precipitation_mm": col("precipitation_sum")[i] or 0,
            "precipitation_probability": col("precipitation_probability_max")[i] or 0,
            "wind_kmh": col("wind_speed_10m_max")[i] or 0,
            "weather_code": col("weather_code")[i],
        }
        d["color"], d["pictogram"] = _day_assessment(d)
        days.append(d)
    if not days:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Prévisions météo vides.")

    next3 = days[:3]
    today = days[0]
    rain3 = sum(d["precipitation_mm"] for d in next3)
    red = next((d for d in next3 if d["color"] == "red"), None)
    sowing_ok = red is None and 10 <= rain3 <= 60
    # Pas de traitement si la pluie risque de lessiver le produit, ou si le vent le disperse
    spraying_ok = today["precipitation_probability"] < 60 and today["precipitation_mm"] < 5 and today["wind_kmh"] < 20

    if red:
        messages = {
            "rain_heavy": "Fortes pluies prévues : risque d'inondation. Ne semez pas et ne traitez pas.",
            "wind": "Vent très fort prévu : ne traitez pas et protégez les jeunes plants.",
            "heat": "Très forte chaleur prévue : arrosez tôt le matin ou le soir.",
        }
        summary = {"color": "red", "indicator": "Alerte", "pictogram": red["pictogram"], "message": messages[red["pictogram"]]}
    elif rain3 < 2 and max(d["precipitation_probability"] for d in next3) < 30:
        summary = {"color": "orange", "indicator": "Temps sec", "pictogram": "sun",
                   "message": "Pas de pluie prévue dans les 3 jours : attendez la pluie pour semer, ou arrosez."}
    elif any(d["color"] == "orange" for d in next3):
        o = next(d for d in next3 if d["color"] == "orange")
        summary = {"color": "orange", "indicator": "Vigilance", "pictogram": o["pictogram"],
                   "message": "Conditions difficiles prévues : surveillez vos cultures."}
    elif sowing_ok:
        summary = {"color": "green", "indicator": "Favorable aux semis", "pictogram": "seed",
                   "message": "Pluies modérées prévues : bon moment pour semer."}
    else:
        summary = {"color": "green", "indicator": "Conditions normales", "pictogram": today["pictogram"],
                   "message": "Pas d'alerte météo pour les 3 prochains jours."}

    summary.update({"sowing_favorable": sowing_ok, "spraying_advised": spraying_ok, "rain_next_3_days_mm": round(rain3, 1)})
    return days, summary


async def forecast(latitude: float, longitude: float) -> dict:
    lat, lon = round(latitude, 2), round(longitude, 2)  # ~1 km : mutualise le cache entre voisins
    data = await _cached(
        f"fc:{lat}:{lon}", settings.WEATHER_CACHE_MINUTES * 60, settings.OPEN_METEO_FORECAST_URL,
        {"latitude": lat, "longitude": lon, "daily": _DAILY_VARS, "timezone": "auto", "forecast_days": 7},
    )
    days, summary = evaluate(data.get("daily") or {})
    return {"latitude": lat, "longitude": lon, "summary": summary, "days": days, "source": "Open-Meteo", "is_simulation": False}
