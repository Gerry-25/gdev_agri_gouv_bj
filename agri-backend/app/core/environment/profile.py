"""Assemble le profil environnemental d'un terrain à partir de son contour."""
import asyncio

from app.core.environment import access, climate, relief, soil, zones
from app.core.utils import utcnow


def sample_points(poly, n: int = 4) -> list[tuple[float, float]]:
    """Centre + quelques sommets répartis (lat, lon) pour les données de sol."""
    c = poly.centroid
    ring = list(poly.exterior.coords)[:-1]
    step = max(1, len(ring) // n)
    return [(c.y, c.x)] + [(y, x) for x, y in ring[::step][:n]]


async def collect(poly, department: str, commune: str, confirmed_zone: int | None = None, full: bool = True) -> dict:
    c = poly.centroid
    tasks = [soil.soil_profile(sample_points(poly) if full else [(c.y, c.x)]), climate.climate_history(c.y, c.x)]
    if full:
        tasks += [relief.relief(poly), access.accessibility(c.y, c.x)]
    results = await asyncio.gather(*tasks)
    env = {"soil": results[0], "climate": results[1], "zone": zones.suggest(department, commune, confirmed_zone), "fetched_at": utcnow()}
    if full:
        env.update(relief=results[2], access=results[3])
    env["soil_reading"] = soil.interpret(env["soil"])
    return env


def availability(env: dict | None) -> dict:
    env = env or {}
    return {k: (env.get(k) or {}).get("status", "absent") for k in ("soil", "climate", "relief", "access")}
