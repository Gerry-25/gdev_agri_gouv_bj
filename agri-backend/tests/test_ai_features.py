import io
from datetime import date, datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.core import ai, ai_service, external
from app.core.config import settings
from app.core.environment import soil
from tests.conftest import (V, create_land, diagnose, domain_payload, login, make_agent, make_eligible_farmer, make_supervisor, png_bytes, run)
from tests.fakes import FakeGemini, fake_external

SURVEY = {"survey_date": "2026-09-01", "agroecological_zone": 6, "land_use_history": "jachere", "fallow_years": 4,
          "last_crops": ["Maïs"], "water_sources": ["riviere"], "flooding_observed": "occasionnel", "vegetation_cover": "arbustive",
          "rainy_season_access": "difficile", "labor_availability": "bonne", "customary_uses": "Passage de bétail en saison sèche"}
ORIENTATION = {"vocation": "mixte", "priority_crops": ["Soja", "Maïs"], "excluded_crops": ["Coton"], "investment_level": "moyen",
               "mechanization": "attelee", "min_valorization_pct": 80}


@pytest.fixture
def gemini(monkeypatch):
    g = FakeGemini()
    monkeypatch.setattr(ai, "ai_client", g)
    return g


@pytest.fixture
def ext(monkeypatch):
    fn, calls = fake_external()
    monkeypatch.setattr(external, "request_json", fn)
    monkeypatch.setattr(settings, "ISDA_USERNAME", "demo")
    monkeypatch.setattr(settings, "ISDA_PASSWORD", "demo")
    external._cache.clear()
    soil._token.update(value=None, expires=0)
    return calls


def no_personal_data(prompts, *secrets):
    for p in prompts:
        for s in secrets:
            assert s not in p, f"donnée personnelle envoyée à l'IA : {s}"


def test_strip_personal():
    ctx = {"npi_owner": "1111111111", "a": [{"phone": "+229", "b": 1}], "farmer_name": "Awa", "keep": "ok"}
    assert ai_service.strip_personal(ctx) == {"a": [{"b": 1}], "keep": "ok"}


# --- Terres de l'État ---------------------------------------------------------------

def test_domain_plan_full_flow(client, db, gemini, ext):
    agent, agent2 = make_agent(client, db), make_agent(client, db, "9999999998", "0199999998")
    dom = client.post(f"{V}/domains", headers=agent, json=domain_payload(6.70, 2.45)).json()
    did = dom["id"]

    ready = client.get(f"{V}/domains/{did}/readiness", headers=agent).json()
    assert not ready["ready"]
    r = client.post(f"{V}/domains/{did}/plans", headers=agent)
    assert r.status_code == 422 and "Relevé de terrain" in r.json()["detail"]["reasons"]

    env = client.post(f"{V}/domains/{did}/environment", headers=agent).json()
    assert env["availability"] == {"soil": "ok", "climate": "ok", "relief": "ok", "access": "ok"}
    e = env["environment"]
    assert e["climate"]["data"]["bimodal"] and e["access"]["data"]["route"]["name"] == "RNIE1"
    assert any(x["level"] == "acide" for x in e["soil_reading"])
    assert [c["zone"] for c in e["zone"]["candidates"]] == [6, 8], "Ouémé hors liste zone 6 : zones candidates"

    assert client.put(f"{V}/domains/{did}/survey", headers=agent, json=SURVEY).status_code == 200
    assert client.put(f"{V}/domains/{did}/orientation", headers=agent, json=ORIENTATION).json()["readiness"]["ready"]
    for i in range(2):
        r = client.post(f"{V}/domains/{did}/photos", headers=agent, data={"caption": f"vue {i}"}, files={"file": ("p.png", png_bytes(), "image/png")})
        assert r.status_code == 201
    assert client.get(r.json()["url"], headers=agent).headers["content-type"] == "image/jpeg"

    plan = client.post(f"{V}/domains/{did}/plans", headers=agent).json()
    assert plan["version"] == 1 and plan["status"] == "proposition" and plan["model"] == settings.GEMINI_PLAN_MODEL
    assert plan["plan"]["recommended_scenario_index"] == 1, "index hors limites ramené au dernier scénario"
    maize = plan["plan"]["scenarios"][0]["yields"][0]["yield_kg_ha"]
    assert maize["low"] <= maize["high"], "fourchette inversée corrigée"
    assert plan["data_used"]["photos"] == 2
    call = gemini.calls[-1]
    assert len(call["contents"]) == 3, "prompt + 2 photos envoyés à l'IA"
    no_personal_data([call["contents"][0]], "9999999999", "0199999999")
    assert "Coton" in call["contents"][0] and "Riz" in call["contents"][0], "exclusions et filières soutenues transmises"

    # Relecture : pas par l'auteur du plan
    review = {"status": "valide", "expert_name": "Dr K. Adjovi", "organization": "INRAB", "note": "Plan cohérent, chaulage à confirmer"}
    assert client.patch(f"{V}/domains/plans/{plan['id']}/review", headers=agent, json=review).status_code == 403
    assert client.patch(f"{V}/domains/plans/{plan['id']}/review", headers=agent2, json=review).json()["status"] == "valide"

    draft = client.get(f"{V}/domains/plans/{plan['id']}/call-draft", headers=agent).json()
    assert draft["warning"] is None and "Surface cultivée" in draft["cahier_des_charges"] and "Maïs" in draft["allowed_crops"]

    # Appel publié avec le plan : résumé visible des candidats
    sup = make_supervisor(client, db)
    now = datetime.now(timezone.utc)
    body = {"title": draft["title"], "description": draft["description"], "cahier_des_charges": draft["cahier_des_charges"],
            "allowed_crops": draft["allowed_crops"], "duration_years": 5, "annual_fee_fcfa_per_ha": 10000,
            "mise_en_valeur_months": draft["mise_en_valeur_months"], "min_score": 40, "plan_id": plan["id"],
            "opens_at": now.isoformat(), "closes_at": (now + timedelta(days=20)).isoformat()}
    c = client.post(f"{V}/domains/{did}/calls", headers=agent, json=body).json()
    client.post(f"{V}/calls/{c['id']}/publish", headers=sup)
    public = client.get(f"{V}/calls/{c['id']}").json()
    assert public["plan_summary"]["recommended_scenario"] == "Vivrier" and public["plan_summary"]["reviewed_by"] == "INRAB"

    farmer, _ = make_eligible_farmer(client, db, "1111111111", "0161000001", 6.58, 2.55)
    app = client.post(f"{V}/calls/{c['id']}/applications", headers=farmer,
                      json={"proposed_crop": "Maïs", "planned_yield_kg": 200000, "motivation": "Dix ans d'expérience en maïs."}).json()
    rev = client.post(f"{V}/calls/{c['id']}/applications/{app['id']}/ai-review", headers=agent).json()
    assert rev["alignment"] == "fort" and "optimiste" in rev["yield_check"], "contrôle déterministe du rendement"
    no_personal_data([gemini.calls[-1]["contents"][0]], "1111111111", "0161000001", "Test Exploitant")


def test_plan_without_soil_service(client, db, gemini, ext, monkeypatch):
    monkeypatch.setattr(settings, "ISDA_USERNAME", "")
    agent = make_agent(client, db)
    did = client.post(f"{V}/domains", headers=agent, json=domain_payload(6.70, 2.45)).json()["id"]
    env = client.post(f"{V}/domains/{did}/environment", headers=agent).json()
    assert env["availability"]["soil"] == "non_configure"
    client.put(f"{V}/domains/{did}/survey", headers=agent, json=SURVEY)
    client.put(f"{V}/domains/{did}/orientation", headers=agent, json=ORIENTATION)
    assert client.post(f"{V}/domains/{did}/plans", headers=agent).status_code == 201, "le sol manquant n'empêche pas le plan"


def test_ai_disabled_returns_503(client, db, ext):
    agent = make_agent(client, db)
    did = client.post(f"{V}/domains", headers=agent, json=domain_payload(6.70, 2.45)).json()["id"]
    client.put(f"{V}/domains/{did}/survey", headers=agent, json=SURVEY)
    client.put(f"{V}/domains/{did}/orientation", headers=agent, json=ORIENTATION)
    assert client.post(f"{V}/domains/{did}/plans", headers=agent).status_code == 503


def test_cache_and_quota(client, db, gemini, ext, monkeypatch):
    h = login(client, "1111111111")
    land = create_land(client, h)
    monkeypatch.setattr(settings, "AI_DAILY_QUOTA_PER_USER", 1)
    body = {"organic_resources": ["compost"]}
    assert client.post(f"{V}/lands/{land['id']}/fertilization-plans", headers=h, json=body).status_code == 201
    assert client.post(f"{V}/lands/{land['id']}/fertilization-plans", headers=h, json=body).status_code == 201, "réponse en cache : pas de quota"
    assert len(gemini.calls) == 1
    r = client.post(f"{V}/lands/{land['id']}/fertilization-plans", headers=h, json={"organic_resources": ["fumier"]})
    assert r.status_code == 429


# --- Parcelle -----------------------------------------------------------------------

def test_soil_and_fertilization(client, db, gemini, ext):
    h, other = login(client, "1111111111"), login(client, "2222222222", phone="0162000000")
    land = create_land(client, h)
    soil_view = client.get(f"{V}/lands/{land['id']}/soil", headers=h).json()
    assert soil_view["reading"][0]["parameter"] == "pH" and "relief" not in soil_view["environment"], "collecte légère pour une parcelle"
    assert client.get(f"{V}/lands/{land['id']}/soil", headers=other).status_code == 403
    assert client.post(f"{V}/lands/{land['id']}/fertilization-plans", headers=other, json={}).status_code == 403
    p = client.post(f"{V}/lands/{land['id']}/fertilization-plans", headers=h, json={"organic_resources": ["compost"], "budget_level": "faible"}).json()
    assert p["plan"]["mineral_inputs"][0]["product"].startswith("NPK") and p["status"] == "proposition"
    assert len(client.get(f"{V}/lands/{land['id']}/fertilization-plans", headers=h).json()) == 1
    audio = client.get(f"{V}/lands/{land['id']}/fertilization-plans/latest/audio", headers=h)
    assert audio.headers["content-type"] == "audio/mpeg"


# --- Assistant ------------------------------------------------------------------------

def test_assistant_only_uses_verified_guides(client, db, gemini):
    h = login(client, "1111111111")
    r = client.post(f"{V}/assistant/ask", headers=h, json={"question": "Comment préparer un extrait de neem ?"}).json()
    assert r["covered"] is False and not gemini.calls, "fiche neem non validée : pas d'appel à l'IA"
    r = client.post(f"{V}/assistant/ask", headers=h, json={"question": "Comment enregistrer ma parcelle avec le GPS ?"}).json()
    assert r["covered"] and r["used_sources"] == ["enregistrer-parcelle-gps"], "source inventée retirée"
    assert r["sources"][0]["verified"] is True
    assert client.get(r["audio_url"], headers=h).headers["content-type"] == "audio/mpeg"
    assert len(client.get(f"{V}/assistant/history", headers=h).json()) == 2


def test_assistant_voice(client, db, gemini):
    h = login(client, "1111111111")
    r = client.post(f"{V}/assistant/ask-voice", headers=h, files={"file": ("q.webm", b"\x1a\x45\xdf\xa3" * 100, "audio/webm")})
    assert r.status_code == 200 and r.json()["transcript"].startswith("Comment") and r.json()["via_voice"]
    assert gemini.calls[0]["contents"][1] is not None, "audio transmis à l'IA"
    assert client.post(f"{V}/assistant/ask-voice", headers=h, files={"file": ("q.txt", b"x", "text/plain")}).status_code == 415


# --- Agents ------------------------------------------------------------------------------

def test_dispute_summary_is_anonymised(client, db, gemini):
    a, b = login(client, "1111111111"), login(client, "2222222222", phone="0162000000")
    agent = make_agent(client, db)
    create_land(client, a)
    from tests.conftest import land_payload, square
    client.post(f"{V}/lands/", headers=b, json=land_payload(square(6.5805, 2.5495)))
    d = client.get(f"{V}/lands/disputes", headers=agent).json()[0]
    s = client.post(f"{V}/lands/disputes/{d['id']}/ai-summary", headers=agent).json()
    assert s["neutral_summary"] and "partie A" in s["parties"]
    prompt = gemini.calls[-1]["contents"][0]
    assert "partie A" in prompt
    no_personal_data([prompt], "1111111111", "2222222222", "+229")


def test_priorities_and_weekly_report(client, db, gemini):
    a = login(client, "1111111111")
    agent = make_agent(client, db)
    land = create_land(client, a)
    for _ in range(3):
        diagnose(client, a, land_id=land["id"])
    items = client.get(f"{V}/state/inspection-priorities", headers=agent).json()
    kinds = {i["kind"] for i in items}
    assert {"verification", "foyer_sanitaire"} <= kinds and items[0]["kind"] == "foyer_sanitaire"
    rep = client.post(f"{V}/state/reports/weekly", headers=agent).json()
    assert rep["report"]["priority_actions"][0]["zone"] == "Dangbo"
    assert len(client.get(f"{V}/state/reports", headers=agent).json()) == 1
    assert client.get(f"{V}/state/inspection-priorities", headers=a).status_code == 403


def test_concession_review(client, db, gemini):
    agent = make_agent(client, db)
    start = datetime.now(timezone.utc) - timedelta(days=400)
    call_id = run(db.calls.insert_one({"title": "x", "status": "concede"})).inserted_id
    cid = run(db.concessions.insert_one({
        "call_id": str(call_id), "domain_id": str(ObjectId()), "domain_name": "Ferme", "department": "Ouémé", "commune": "Dangbo",
        "surface_hectares": 10, "farmer_npi": "1111111111", "crop_type": "Maïs", "planned_yield_kg": 20000, "duration_years": 5,
        "annual_fee_fcfa": 150000, "status": "active", "start_date": start, "end_date": start + timedelta(days=5 * 365),
        "mise_en_valeur_deadline": start + timedelta(days=365), "latest_mise_en_valeur_pct": 30, "payments": [],
        "cahier_des_charges": "80 % sous 12 mois", "created_at": start})).inserted_id
    r = client.post(f"{V}/concessions/{cid}/ai-review", headers=agent).json()
    assert r["assessment"] == "a_surveiller"
    prompt = gemini.calls[-1]["contents"][0]
    assert '"mise_en_valeur_alert": true' in prompt and "1111111111" not in prompt
    items = client.get(f"{V}/state/inspection-priorities", headers=agent).json()
    assert any(i["kind"] == "concession" and "redevance impayée" in i["reason"] for i in items)


# --- Stockage ---------------------------------------------------------------------------

def test_storage_advisor(client, db, gemini):
    h = login(client, "1111111111")
    agent = make_agent(client, db)
    land = create_land(client, h)
    old = (date.today() - timedelta(days=40)).isoformat()
    safe = client.post(f"{V}/storage/lots", headers=h, json={"product": "Maïs", "quantity_kg": 500, "harvest_date": old,
                                                             "storage_method": "sac_hermetique", "moisture_pct": 12, "land_id": land["id"]}).json()
    assert safe["risk"]["level"] == "faible" and safe["department"] == "Ouémé"
    risky = client.post(f"{V}/storage/lots", headers=h, json={"product": "Maïs", "quantity_kg": 800, "harvest_date": old,
                                                              "storage_method": "grenier_traditionnel", "moisture_pct": 17, "land_id": land["id"],
                                                              "client_ref": "offline-stock-0001"}).json()
    assert risky["risk"]["level"] == "eleve" and any("Humidité 17" in f for f in risky["risk"]["factors"])
    dup = client.post(f"{V}/storage/lots", headers=h, json={"product": "Maïs", "quantity_kg": 800, "harvest_date": old,
                                                            "storage_method": "grenier_traditionnel", "land_id": land["id"], "client_ref": "offline-stock-0001"})
    assert dup.status_code == 200 and dup.json()["id"] == risky["id"]

    client.get(f"{V}/storage/lots/me", headers=h)
    client.get(f"{V}/storage/lots/me", headers=h)
    reminders = [n for n in client.get(f"{V}/notifications/me", headers=h).json() if n["type"] == "storage_check"]
    assert len(reminders) == 2, "un rappel par stock à contrôler, pas de doublon"

    checked = client.post(f"{V}/storage/lots/{risky['id']}/checks", headers=h, json={"moisture_pct": 13, "insects_seen": False}).json()
    assert checked["risk"]["level"] in ("moyen", "eleve") and len(checked["checks"]) == 1
    adv = client.post(f"{V}/storage/lots/{risky['id']}/advice", headers=h).json()
    assert adv["sell_or_store"] == "vendre_en_partie" and adv["risk"]["level"]
    client.patch(f"{V}/storage/lots/{risky['id']}/status", headers=h, json={"status": "perdu"})
    ov = client.get(f"{V}/storage/overview", headers=agent).json()
    assert ov[0]["lost_kg"] == 800 and ov[0]["loss_rate_pct"] == 61.5
    assert client.get(f"{V}/storage/overview", headers=h).status_code == 403


# --- Diagnostic et marché ------------------------------------------------------------------

def test_diagnosis_followup(client, db, gemini):
    h = login(client, "1111111111")
    alert = diagnose(client, h, department="Ouémé", commune="Dangbo").json()["alert_id"]
    r = client.post(f"{V}/monitoring/diagnoses/{alert}/ask", headers=h, json={"question": "Faut-il recommencer après la pluie ?"}).json()
    assert r["see_advisor"] is False
    assert len(gemini.calls[-1]["contents"]) == 2, "photo du diagnostic jointe"
    stored = run(db.phytosanitary_alerts.find_one({"_id": ObjectId(alert)}))
    assert stored["qa"][0]["question"].startswith("Faut-il")


def test_market_price_suggestion_and_draft(client, db, gemini):
    h = login(client, "1111111111")
    offer = {"product_name": "Maïs blanc", "quantity_kg": 1000, "contact_phone": "0161000000", "location_commune": "Allada", "department": "Atlantique"}
    for price in (200, 240):
        client.post(f"{V}/market/offers", headers=h, json={**offer, "unit_price_fcfa": price})
    s = client.get(f"{V}/market/price-suggestion?product=maïs&department=Atlantique").json()
    assert s["reference_avg_fcfa_kg"] == 220 and s["suggested_min_fcfa_kg"] == 200 and s["scope"] == "departement"
    assert client.get(f"{V}/market/price-suggestion?product=vanille").json()["observations"] == 0
    d = client.post(f"{V}/market/offers/ai-draft", headers=h, data={"notes": "maïs blanc bien sec", "quantity_kg": "500", "department": "Atlantique"},
                    files={"file": ("p.png", png_bytes(), "image/png")}).json()
    assert d["listing_text"] and d["price"]["reference_avg_fcfa_kg"] == 220 and d["status"] == "proposition"
