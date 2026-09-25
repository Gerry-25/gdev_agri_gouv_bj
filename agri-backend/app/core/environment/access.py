"""Accessibilité : distances aux routes, cours d'eau et marchés (OpenStreetMap, via Overpass)."""
from shapely.geometry import LineString, Point

from app.core import external, geo
from app.core.config import settings

SOURCE = "OpenStreetMap (Overpass)"
RADIUS_M = 15_000


def _query(lat: float, lon: float) -> str:
    a = f"(around:{RADIUS_M},{lat:.5f},{lon:.5f})"
    return (
        "[out:json][timeout:25];("
        f'way{a}["highway"~"^(trunk|primary|secondary|tertiary)$"];'
        f'way{a}["waterway"~"^(river|stream|canal)$"];'
        f'node{a}["amenity"="marketplace"];way{a}["amenity"="marketplace"];'
        ");out geom 400;"
    )


def _category(tags: dict) -> str | None:
    if "highway" in tags:
        return "route"
    if "waterway" in tags:
        return "cours_eau"
    if tags.get("amenity") == "marketplace":
        return "marche"
    return None


def distances(elements: list[dict], lat: float, lon: float) -> dict:
    origin = geo.to_utm(Point(lon, lat))
    best: dict[str, dict] = {}
    for el in elements:
        cat = _category(el.get("tags") or {})
        if not cat:
            continue
        if el.get("geometry"):
            coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
            shape = LineString(coords) if len(coords) > 1 else Point(coords[0])
        elif "lat" in el:
            shape = Point(el["lon"], el["lat"])
        else:
            continue
        d = geo.to_utm(shape).distance(origin)
        if cat not in best or d < best[cat]["distance_km"] * 1000:
            best[cat] = {"distance_km": round(d / 1000, 2), "name": (el.get("tags") or {}).get("name")}
    return {cat: best.get(cat) for cat in ("route", "cours_eau", "marche")}


async def accessibility(lat: float, lon: float) -> dict:
    try:
        data = await external.cached_json("POST", settings.OVERPASS_URL, ttl_s=30 * 86400, timeout=40,
                                          data={"data": _query(lat, lon)})
        d = distances(data.get("elements") or [], lat, lon)
    except (external.ExternalUnavailable, KeyError, TypeError) as e:
        return external.result("indisponible", SOURCE, error=str(e))
    d["note"] = f"Recherche dans un rayon de {RADIUS_M // 1000} km ; absence = rien de cartographié dans OpenStreetMap."
    return external.result("ok", SOURCE, data=d)
