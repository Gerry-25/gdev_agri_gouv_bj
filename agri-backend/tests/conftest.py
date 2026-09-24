"""Environnement de test : base MongoDB en mémoire (mongomock), IA et météo simulées.

Lancer : pip install -r requirements-dev.txt && pytest
"""
import asyncio
import io
import os

os.environ.update(
    MONGODB_URL="mongodb://test",
    JWT_SECRET_KEY="test-secret-" + "x" * 40,
    GEMINI_API_KEY="",
    CORS_ORIGINS="http://localhost:3000",
    OTP_RESEND_SECONDS="0",
)

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.core import ai, database, geo  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.knowledge.seed import seed_guides  # noqa: E402
from app.modules.lands import service  # noqa: E402
from app.modules.monitoring import weather  # noqa: E402
from app.modules.monitoring.schemas import DiagnosisResult  # noqa: E402

V = "/api/v1"


def run(coro):
    return asyncio.run(coro)


async def _fake_candidates(db, geojson, exclude_id=None):
    """mongomock ne gère pas $geoIntersects : présélection équivalente avec shapely."""
    poly = geo.from_geojson(geojson)
    return [d async for d in db["lands"].find({}) if d["_id"] != exclude_id and geo.from_geojson(d["boundary"]).intersects(poly)]


FORECAST = {"daily": {
    "time": ["2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27"],
    "temperature_2m_max": [31, 32, 31, 30], "temperature_2m_min": [24, 24, 23, 23],
    "precipitation_sum": [0, 12, 8, 70], "precipitation_probability_max": [20, 70, 60, 90],
    "wind_speed_10m_max": [10, 12, 14, 20], "weather_code": [1, 61, 61, 65],
}}


@pytest.fixture
def db(monkeypatch):
    database_ = AsyncMongoMockClient()["test"]
    database.db.db = database_
    run(database.create_indexes(database_))
    run(seed_guides(database_))
    monkeypatch.setattr(service, "candidate_lands", _fake_candidates)
    monkeypatch.setattr(ai, "ai_client", None)
    weather._cache.clear()
    calls = []

    async def fake_json(url, params):
        calls.append(url)
        if "geocoding" in url:
            return {"results": [{"name": "Dangbo", "admin1": "Ouémé", "latitude": 6.58, "longitude": 2.55, "country_code": "BJ"}]}
        return FORECAST

    monkeypatch.setattr(weather, "_get_json", fake_json)
    database_.weather_calls = calls
    return database_


@pytest.fixture
def client(db):
    return TestClient(app)


@pytest.fixture
def fake_ai(monkeypatch):
    """Client Gemini simulé : diagnostic 'Critique' et audio PCM."""
    state = {"diagnoses": 0, "tts": 0, "result": DiagnosisResult(
        crop_identified="Maïs", health_status="Attaque parasitaire", disease_name="Chenille légionnaire",
        severity="Critique", simple_summary="Une chenille mange le maïs.", treatment_steps=["Piler du neem", "Pulvériser le soir"],
        treatment_advice="Neem.", confidence_score=0.8)}

    async def generate(**kw):
        if getattr(kw.get("config"), "response_modalities", None):
            state["tts"] += 1
            part = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x00\x10" * 24000))
            return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])
        state["diagnoses"] += 1
        return SimpleNamespace(parsed=state["result"], text=state["result"].model_dump_json())

    monkeypatch.setattr(ai, "ai_client", SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate))))
    return state


# --- Aides -----------------------------------------------------------------------

def login(client, npi, phone="0161000000", role="farmer", full_name="Test Exploitant", **extra):
    r = client.post(f"{V}/auth/otp/request", json={"npi": npi, "phone": phone, "full_name": full_name, "role": role, **extra})
    assert r.status_code == 200, r.text
    r = client.post(f"{V}/auth/otp/verify", json={"npi": npi, "code": r.json()["simulated_code"]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_agent(client, db, npi="9999999999", phone="0199999999"):
    login(client, npi, phone=phone)
    run(db.users.update_one({"npi": npi}, {"$set": {"role": "state_agent"}}))
    return login(client, npi, phone=phone)


def square(lat, lon, d=0.0009):
    """Carré d'environ 100 m de côté, avec des points intermédiaires."""
    pts = [(lat, lon), (lat, lon + d / 2), (lat, lon + d), (lat + d / 2, lon + d),
           (lat + d, lon + d), (lat + d, lon + d / 2), (lat + d, lon), (lat + d / 2, lon)]
    return [{"latitude": a, "longitude": b, "accuracy_m": 4} for a, b in pts]


def land_payload(pts, **kw):
    return {"department": "oueme", "commune": "dangbo", "crop_type": "Manioc", "estimated_yield_kg": 8000,
            "boundary": {"points": pts}, **kw}


def create_land(client, headers, lat=6.58, lon=2.55, **kw):
    r = client.post(f"{V}/lands/", headers=headers, json=land_payload(square(lat, lon), **kw))
    assert r.status_code == 201, r.text
    return r.json()


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (60, 60), "green").save(buf, "PNG")
    return buf.getvalue()


def diagnose(client, headers, **form):
    return client.post(f"{V}/monitoring/diagnose", headers=headers, data=form, files={"file": ("f.png", png_bytes(), "image/png")})
