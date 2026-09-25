"""Appels aux services externes (sol, climat, relief, cartographie), avec cache mémoire.

Une panne d'un service n'empêche jamais le reste de fonctionner : les connecteurs renvoient un
statut « indisponible » que l'IA et l'interface savent interpréter.
"""
import hashlib
import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)
_cache: dict[str, tuple[float, object]] = {}


class ExternalUnavailable(Exception):
    pass


async def request_json(method: str, url: str, *, params=None, data=None, headers=None, timeout: float = 20) -> object:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.request(method, url, params=params, data=data, headers=headers)
        r.raise_for_status()
        return r.json()


async def cached_json(method: str, url: str, *, ttl_s: float, params=None, data=None, headers=None, timeout: float = 20) -> object:
    key = hashlib.sha256(json.dumps([method, url, params, data], sort_keys=True, default=str).encode()).hexdigest()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl_s:
        return hit[1]
    try:
        value = await request_json(method, url, params=params, data=data, headers=headers, timeout=timeout)
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Service externe indisponible (%s) : %s", url, e)
        raise ExternalUnavailable(str(e)) from e
    _cache[key] = (time.monotonic(), value)
    return value


def result(status: str, source: str, data=None, error: str | None = None) -> dict:
    """Format commun des connecteurs : status = ok | partiel | indisponible | non_configure."""
    return {"status": status, "source": source, "data": data, "error": error}
