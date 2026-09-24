from datetime import datetime, timedelta, timezone

from tests.conftest import V, create_land, diagnose, login, make_agent, run


def test_location_is_required(client):
    h = login(client, "1111111111")
    assert diagnose(client, h).status_code == 422
    assert diagnose(client, h, commune="Dangbo", department="Ouémé", latitude="6.5").status_code == 422
    assert diagnose(client, h, commune="Dangbo", department="Ouémé", latitude="48.8", longitude="2.3").status_code == 422


def test_simulation_mode_not_stored(client, db):
    h = login(client, "1111111111")
    land = create_land(client, h)
    r = diagnose(client, h, land_id=land["id"])
    assert r.json()["is_simulation"] and r.json()["commune"] == "Dangbo"
    assert run(db.phytosanitary_alerts.count_documents({})) == 0


def test_real_diagnosis_stored_with_image_and_language(client, db, fake_ai):
    h = login(client, "1111111111", preferred_language="fon")
    other = login(client, "2222222222", phone="0162000000")
    land = create_land(client, h)
    assert diagnose(client, other, land_id=land["id"]).status_code == 403
    r = diagnose(client, h, land_id=land["id"]).json()
    assert r["alert_color"] == "red" and r["language"] == "fon", "langue du profil par défaut"
    assert r["location"]["type"] == "Point" and r["image_url"].endswith("/image")
    img = client.get(r["image_url"], headers=h)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get(r["image_url"], headers=other).status_code == 403
    assert len(client.get(f"{V}/monitoring/diagnoses/me", headers=h).json()) == 1


def test_offline_resend_and_captured_at(client, db, fake_ai):
    h = login(client, "1111111111")
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    form = {"department": "Zou", "commune": "abomey", "client_ref": "offline-diag-0001", "captured_at": past}
    first = diagnose(client, h, **form).json()
    again = diagnose(client, h, **form).json()
    assert first["alert_id"] == again["alert_id"] and fake_ai["diagnoses"] == 1, "pas de second appel à l'IA"
    assert first["observed_at"].startswith(past[:10])
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert diagnose(client, h, department="Zou", commune="Abomey", captured_at=future).status_code == 422
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    assert diagnose(client, h, department="Zou", commune="Abomey", captured_at=old).status_code == 422


def test_hotspot_notifies_farmers_and_agents(client, db, fake_ai):
    a, neighbour = login(client, "1111111111"), login(client, "2222222222", phone="0162000000")
    agent = make_agent(client, db)
    land = create_land(client, a)
    create_land(client, neighbour, 6.60, 2.57)
    for _ in range(3):
        diagnose(client, a, land_id=land["id"])
    for h in (neighbour, agent):
        notes = client.get(f"{V}/notifications/me", headers=h).json()
        assert [n["type"] for n in notes] == ["sanitary_alert"], "une seule alerte au franchissement du seuil"
    diagnose(client, a, land_id=land["id"])
    assert client.get(f"{V}/notifications/me/unread-count", headers=neighbour).json()["unread"] == 1


def test_audio_mp3_cached(client, db, fake_ai):
    h = login(client, "1111111111")
    alert = diagnose(client, h, department="Ouémé", commune="Dangbo").json()["alert_id"]
    r = client.get(f"{V}/monitoring/diagnoses/{alert}/audio", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) < 20_000
    client.get(f"{V}/monitoring/diagnoses/{alert}/audio", headers=h)
    assert fake_ai["tts"] == 1, "audio servi depuis le cache"
    wav = client.get(f"{V}/monitoring/diagnoses/{alert}/audio?format=wav", headers=h)
    assert wav.content[:4] == b"RIFF"


def test_audio_unavailable_without_key(client, db, fake_ai, monkeypatch):
    h = login(client, "1111111111")
    alert = diagnose(client, h, department="Ouémé", commune="Dangbo").json()["alert_id"]
    from app.core import ai
    monkeypatch.setattr(ai, "ai_client", None)
    assert client.get(f"{V}/monitoring/diagnoses/{alert}/audio", headers=h).status_code == 503


def test_upload_validation(client):
    h = login(client, "1111111111")
    loc = {"department": "Ouémé", "commune": "Dangbo"}
    assert client.post(f"{V}/monitoring/diagnose", headers=h, data=loc, files={"file": ("a.png", b"pas une image", "image/png")}).status_code == 400
    assert client.post(f"{V}/monitoring/diagnose", headers=h, data=loc, files={"file": ("a.txt", b"x", "text/plain")}).status_code == 415
    assert client.post(f"{V}/monitoring/diagnose", headers=h, data=loc, files={"file": ("a.png", b"0" * (6 * 1024 * 1024), "image/png")}).status_code == 413


def test_ai_failure_returns_502(client, monkeypatch, fake_ai):
    from types import SimpleNamespace
    from app.core import ai

    async def boom(**kw):
        raise RuntimeError("secret interne")
    monkeypatch.setattr(ai, "ai_client", SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=boom))))
    r = diagnose(client, login(client, "1111111111"), department="Ouémé", commune="Dangbo")
    assert r.status_code == 502 and "secret" not in r.text


def test_weather(client, db):
    h = login(client, "1111111111")
    w = client.get(f"{V}/monitoring/weather-alerts/Dangbo").json()
    assert w["summary"]["color"] == "green" and w["summary"]["sowing_favorable"] and w["days"][3]["color"] == "red"
    client.get(f"{V}/monitoring/weather-alerts/Dangbo")
    assert len(db.weather_calls) == 2, "cache"
    land = create_land(client, h)
    assert client.get(f"{V}/monitoring/weather/land/{land['id']}", headers=h).status_code == 200
    assert client.get(f"{V}/monitoring/weather?latitude=48.8&longitude=2.3").status_code == 422


def test_weather_rules():
    from app.modules.monitoring.weather import evaluate
    assert evaluate({"time": ["a", "b", "c"], "precipitation_sum": [80, 0, 0]})[1]["color"] == "red"
    dry = evaluate({"time": ["a", "b", "c"], "precipitation_sum": [0, 0, 0], "precipitation_probability_max": [5, 5, 5]})[1]
    assert dry["indicator"] == "Temps sec"
    windy = evaluate({"time": ["a"], "wind_speed_10m_max": [25]})[1]
    assert windy["spraying_advised"] is False
