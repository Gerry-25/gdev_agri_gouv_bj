"""Relief : altitude, pente et position dans le paysage (Open-Meteo Elevation, modèle Copernicus 90 m)."""
import math
from statistics import mean

from app.core import external, geo
from app.core.config import settings

SOURCE = "Open-Meteo Elevation (Copernicus DEM)"


def _ring(lat: float, lon: float, radius_m: float, n: int = 8) -> list[tuple[float, float]]:
    return [(lat + radius_m * math.sin(2 * math.pi * i / n) / 110_540,
             lon + radius_m * math.cos(2 * math.pi * i / n) / (111_320 * math.cos(math.radians(lat)))) for i in range(n)]


async def relief(poly) -> dict:
    c = poly.centroid
    vertices = [(y, x) for x, y in list(poly.exterior.coords)[:-1]][:24]
    ring = _ring(c.y, c.x, 500)
    pts = [(c.y, c.x)] + vertices + ring
    try:
        data = await external.cached_json(
            "GET", settings.OPEN_METEO_ELEVATION_URL, ttl_s=365 * 86400,
            params={"latitude": ",".join(f"{p[0]:.5f}" for p in pts), "longitude": ",".join(f"{p[1]:.5f}" for p in pts)},
        )
        elev = data["elevation"]
    except (external.ExternalUnavailable, KeyError, TypeError) as e:
        return external.result("indisponible", SOURCE, error=str(e))

    center, inside, around = elev[0], elev[1:1 + len(vertices)], elev[1 + len(vertices):]
    # Pente approximative : plus grande dénivelée entre sommets rapportée à leur distance
    utm = [geo.to_utm(geo.Point(lon, lat)) for lat, lon in vertices]
    slope = 0.0
    for i in range(len(utm)):
        for j in range(i + 1, len(utm)):
            d = utm[i].distance(utm[j])
            if d > 30:
                slope = max(slope, abs(inside[i] - inside[j]) / d * 100)
    delta = center - mean(around)
    position = "bas de versant ou bas-fond (risque d'engorgement)" if delta < -3 else "sommet ou plateau" if delta > 3 else "versant ou plaine"
    return external.result("ok", SOURCE, data={
        "altitude_m": {"min": round(min(inside + [center])), "max": round(max(inside + [center])), "centre": round(center)},
        "max_slope_pct": round(slope, 1),
        "slope_class": "faible" if slope < 2 else "modérée" if slope < 8 else "forte (risque d'érosion)",
        "landscape_position": position,
        "relative_height_vs_500m_m": round(delta, 1),
    })
