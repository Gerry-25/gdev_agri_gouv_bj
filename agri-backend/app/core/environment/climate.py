"""Climat historique : 10 années complètes d'Open-Meteo (archives, sans clé)."""
from collections import defaultdict
from datetime import date
from statistics import mean

from app.core import external
from app.core.config import settings

SOURCE = "Open-Meteo (archives ERA5)"
MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def _wet_periods(monthly: list[float], threshold: float = 60) -> list[str]:
    """Regroupe les mois consécutifs assez pluvieux : « mars - juil. », « sept. - nov. »."""
    periods, start = [], None
    for i, v in enumerate(monthly + [0]):
        if v >= threshold and start is None:
            start = i
        if v < threshold and start is not None:
            periods.append(f"{MONTHS[start]} - {MONTHS[i - 1]}" if i - 1 > start else MONTHS[start])
            start = None
    return periods


def summarize(daily: dict) -> dict:
    days = daily.get("time") or []
    rain = daily.get("precipitation_sum") or []
    tmax = daily.get("temperature_2m_max") or []
    by_year = defaultdict(float)
    by_month = defaultdict(list)
    month_year = defaultdict(float)
    hot_days = defaultdict(int)
    for i, d in enumerate(days):
        y, m = int(d[:4]), int(d[5:7])
        r = rain[i] or 0
        by_year[y] += r
        month_year[(y, m)] += r
        if (tmax[i] or 0) >= 35:
            hot_days[y] += 1
    for (y, m), total in month_year.items():
        by_month[m].append(total)
    monthly = [round(mean(by_month[m]), 1) if by_month[m] else 0 for m in range(1, 13)]
    years = sorted(by_year)
    # Plus longue période sèche (jours consécutifs < 1 mm) pendant les mois pluvieux, moyenne annuelle
    wet_months = {m + 1 for m, v in enumerate(monthly) if v >= 60}
    spells = defaultdict(int)
    run = 0
    for i, d in enumerate(days):
        if int(d[5:7]) in wet_months:
            run = run + 1 if (rain[i] or 0) < 1 else 0
            spells[int(d[:4])] = max(spells[int(d[:4])], run)
        else:
            run = 0
    return {
        "years": f"{years[0]}-{years[-1]}" if years else None,
        "annual_rainfall_mm": {"mean": round(mean(by_year.values())), "min": round(min(by_year.values())),
                               "max": round(max(by_year.values()))} if by_year else None,
        "monthly_rainfall_mm": dict(zip(MONTHS, monthly)),
        "rainy_seasons": _wet_periods(monthly),
        "bimodal": len(_wet_periods(monthly)) >= 2,
        "hot_days_per_year": round(mean(hot_days.get(y, 0) for y in years)) if years else None,
        "longest_dry_spell_in_rainy_season_days": round(mean(spells.values())) if spells else None,
        "mean_tmax_c": round(mean(t for t in tmax if t is not None), 1) if tmax else None,
    }


async def climate_history(lat: float, lon: float, years: int = 10) -> dict:
    end_year = date.today().year - 1
    try:
        data = await external.cached_json(
            "GET", settings.OPEN_METEO_ARCHIVE_URL, ttl_s=30 * 86400, timeout=40,
            params={"latitude": round(lat, 2), "longitude": round(lon, 2),
                    "start_date": f"{end_year - years + 1}-01-01", "end_date": f"{end_year}-12-31",
                    "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min", "timezone": "auto"},
        )
        return external.result("ok", SOURCE, data=summarize(data.get("daily") or {}))
    except (external.ExternalUnavailable, ValueError, KeyError) as e:
        return external.result("indisponible", SOURCE, error=str(e))
