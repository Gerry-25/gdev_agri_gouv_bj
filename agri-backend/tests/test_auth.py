from tests.conftest import V, login, run


def test_first_login_requires_name_and_creates_user(client, db):
    r = client.post(f"{V}/auth/otp/request", json={"npi": "1111111111", "phone": "0161000000"})
    assert r.status_code == 422
    r = client.post(f"{V}/auth/otp/request", json={"npi": "1111111111", "phone": "0161000000", "full_name": "Awa"})
    body = r.json()
    assert r.status_code == 200 and body["is_new_user"] and body["delivery"] == "simulation" and len(body["simulated_code"]) == 6
    assert run(db.users.count_documents({})) == 0, "l'utilisateur n'est créé qu'après validation du code"
    r = client.post(f"{V}/auth/otp/verify", json={"npi": "1111111111", "code": body["simulated_code"]})
    assert r.status_code == 200 and r.json()["user"]["role"] == "farmer" and r.json()["refresh_token"]


def test_state_agent_cannot_self_assign(client):
    r = client.post(f"{V}/auth/otp/request", json={"npi": "1111111111", "phone": "0161000000", "full_name": "X", "role": "state_agent"})
    assert r.status_code == 422


def test_wrong_phone_and_wrong_code(client):
    login(client, "1111111111")
    assert client.post(f"{V}/auth/otp/request", json={"npi": "1111111111", "phone": "0162000000"}).status_code == 401
    client.post(f"{V}/auth/otp/request", json={"npi": "1111111111", "phone": "0161000000"})
    r = client.post(f"{V}/auth/otp/verify", json={"npi": "1111111111", "code": "000000"})
    assert r.status_code == 400 and "essai" in r.json()["detail"]


def test_too_many_attempts(client, db):
    r = client.post(f"{V}/auth/otp/request", json={"npi": "1111111111", "phone": "0161000000", "full_name": "Awa"})
    good = r.json()["simulated_code"]
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        client.post(f"{V}/auth/otp/verify", json={"npi": "1111111111", "code": bad})
    r = client.post(f"{V}/auth/otp/verify", json={"npi": "1111111111", "code": good})
    assert r.status_code == 429, "même le bon code est refusé après trop d'essais"


def test_resend_cooldown_and_hourly_limit(client, monkeypatch):
    from app.core.config import settings
    payload = {"npi": "1111111111", "phone": "0161000000", "full_name": "Awa"}
    for _ in range(settings.OTP_MAX_PER_HOUR):
        assert client.post(f"{V}/auth/otp/request", json=payload).status_code == 200
    assert client.post(f"{V}/auth/otp/request", json=payload).status_code == 429
    monkeypatch.setattr(settings, "OTP_RESEND_SECONDS", 60)
    assert client.post(f"{V}/auth/otp/request", json=payload).json()["detail"].startswith("Patientez")


def test_phone_normalization(client, db):
    login(client, "4444444444", phone="97000000")
    assert run(db.users.find_one({"npi": "4444444444"}))["phone"] == "+2290197000000"


def test_refresh_rotation_logout_and_role_update(client, db):
    r = client.post(f"{V}/auth/otp/request", json={"npi": "1111111111", "phone": "0161000000", "full_name": "Awa"})
    tokens = client.post(f"{V}/auth/otp/verify", json={"npi": "1111111111", "code": r.json()["simulated_code"]}).json()
    run(db.users.update_one({"npi": "1111111111"}, {"$set": {"role": "state_agent"}}))
    new = client.post(f"{V}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert new.status_code == 200 and new.json()["user"]["role"] == "state_agent", "le rôle est relu en base"
    assert client.post(f"{V}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401, "rotation"
    client.post(f"{V}/auth/logout", json={"refresh_token": new.json()["refresh_token"]})
    assert client.post(f"{V}/auth/refresh", json={"refresh_token": new.json()["refresh_token"]}).status_code == 401


def test_profile_update(client):
    h = login(client, "1111111111")
    r = client.patch(f"{V}/auth/me", headers=h, json={"preferred_language": "fon", "department": "zou", "commune": "bohicon"})
    assert r.json()["preferred_language"] == "fon" and r.json()["department"] == "Zou" and r.json()["commune"] == "Bohicon"
    assert client.get(f"{V}/auth/me").status_code == 401
    assert client.get(f"{V}/auth/me", headers={"Authorization": "Bearer faux"}).status_code == 401
