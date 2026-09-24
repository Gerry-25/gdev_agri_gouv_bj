from bson import ObjectId

from tests.conftest import V, create_land, land_payload, login, make_agent, run, square


def test_register_computes_surface_and_normalizes(client):
    h = login(client, "1111111111")
    land = create_land(client, h)
    assert 0.9 < land["surface_hectares"] < 1.1 and land["status"] == "registered"
    got = client.get(f"{V}/lands/{land['id']}", headers=h).json()
    assert got["department"] == "Ouémé" and got["commune"] == "Dangbo" and got["verification_status"] == "declaree"
    ring = got["boundary"]["coordinates"][0]
    assert ring[0] == ring[-1] and got["boundary"]["type"] == "Polygon"


def test_invalid_geometries(client):
    h = login(client, "1111111111")
    bowtie = [{"latitude": 6.6, "longitude": 2.5}, {"latitude": 6.601, "longitude": 2.501},
              {"latitude": 6.6, "longitude": 2.501}, {"latitude": 6.601, "longitude": 2.5}]
    for pts in (bowtie, square(48.85, 2.35), square(6.7, 2.5, d=0.00005), square(6.7, 2.5)[:2]):
        assert client.post(f"{V}/lands/", headers=h, json=land_payload(pts)).status_code == 422
    assert client.post(f"{V}/lands/", headers=h, json={**land_payload(square(6.7, 2.5)), "department": "Paris"}).status_code == 422


def test_overlaps(client):
    a, b = login(client, "1111111111"), login(client, "2222222222", phone="0162000000")
    l1 = create_land(client, a)
    assert client.post(f"{V}/lands/", headers=a, json=land_payload(square(6.5804, 2.5504))).status_code == 409
    assert create_land(client, b, 6.58, 2.5509)["status"] == "registered", "bordure partagée tolérée"
    r = client.post(f"{V}/lands/", headers=b, json=land_payload(square(6.5805, 2.5495))).json()
    assert r["status"] == "registered_with_dispute" and r["overlaps"][0]["land_id"] == l1["id"]
    assert client.get(f"{V}/lands/{l1['id']}", headers=a).json()["dispute_flag"] is True
    assert client.delete(f"{V}/lands/{l1['id']}", headers=a).status_code == 409
    notes = client.get(f"{V}/notifications/me", headers=a).json()
    assert notes[0]["type"] == "dispute_opened"


def test_client_ref_idempotency(client, db):
    h = login(client, "1111111111")
    body = land_payload(square(6.58, 2.55), client_ref="offline-land-0001")
    first = client.post(f"{V}/lands/", headers=h, json=body)
    again = client.post(f"{V}/lands/", headers=h, json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["status"] == "already_registered" and again.json()["id"] == first.json()["id"]
    assert run(db.lands.count_documents({})) == 1


def test_boundary_update_archives_and_resets_verification(client, db):
    h = login(client, "1111111111")
    agent = make_agent(client, db)
    land = create_land(client, h)
    assert client.patch(f"{V}/lands/{land['id']}/verification", headers=h, json={"status": "verifiee", "note": "ok"}).status_code == 403
    r = client.patch(f"{V}/lands/{land['id']}/verification", headers=agent, json={"status": "verifiee", "note": "Visite terrain"})
    assert r.json()["verification_status"] == "verifiee"
    assert client.put(f"{V}/lands/{land['id']}/boundary", headers=h, json={"points": square(6.59, 2.56)}).json()["status"] == "updated"
    doc = run(db.lands.find_one({"_id": ObjectId(land["id"])}))
    assert len(doc["boundary_history"]) == 1 and doc["verification_status"] == "declaree"


def test_access_rules_and_geojson(client, db):
    a, b = login(client, "1111111111"), login(client, "2222222222", phone="0162000000")
    land = create_land(client, a)
    assert client.get(f"{V}/lands/{land['id']}", headers=b).status_code == 403
    assert client.get(f"{V}/lands/owner/1111111111", headers=b).status_code == 403
    assert client.get(f"{V}/lands/owner/1111111111", headers=make_agent(client, db)).status_code == 200
    fc = client.get(f"{V}/lands/me/geojson", headers=a).json()
    assert fc["type"] == "FeatureCollection" and fc["features"][0]["properties"]["surface_hectares"] > 0
    assert client.get(f"{V}/lands/pas-un-id", headers=a).status_code == 404
    assert client.patch(f"{V}/lands/{land['id']}", headers=a, json={"crop_type": "Maïs"}).json()["crop_type"] == "Maïs"


def test_disputes_workflow(client, db):
    a, buyer = login(client, "1111111111"), login(client, "3333333333", phone="0163000000", role="buyer")
    agent = make_agent(client, db)
    land = create_land(client, a)
    assert client.post(f"{V}/lands/{land['id']}/disputes", headers=a, json={"type": "limite", "reason": "ma propre parcelle"}).status_code == 400
    r = client.post(f"{V}/lands/{land['id']}/disputes", headers=buyer, json={"type": "revendication", "reason": "Terrain hérité de mon père"})
    assert r.status_code == 201
    assert client.get(f"{V}/lands/disputes", headers=a).status_code == 403
    d = client.get(f"{V}/lands/disputes?status=ouvert", headers=agent).json()[0]
    assert client.patch(f"{V}/lands/disputes/{d['id']}", headers=agent, json={"status": "resolu", "resolution_note": "Bornage refait"}).status_code == 200
    assert client.get(f"{V}/lands/{land['id']}", headers=a).json()["dispute_flag"] is False
    assert client.patch(f"{V}/lands/disputes/{d['id']}", headers=agent, json={"status": "rejete", "resolution_note": "xxxxx"}).status_code == 409
    assert client.get(f"{V}/notifications/me/unread-count", headers=buyer).json()["unread"] == 1


def test_transfer_workflow(client, db):
    a, b = login(client, "1111111111"), login(client, "2222222222", phone="0162000000")
    agent = make_agent(client, db)
    land = create_land(client, a)
    assert client.post(f"{V}/lands/{land['id']}/transfers", headers=b, json={"new_owner_npi": "2222222222", "reason": "vente"}).status_code == 403
    assert client.post(f"{V}/lands/{land['id']}/transfers", headers=a, json={"new_owner_npi": "1111111111", "reason": "vente"}).status_code == 400
    t = client.post(f"{V}/lands/{land['id']}/transfers", headers=a, json={"new_owner_npi": "2222222222", "reason": "vente"}).json()
    assert client.post(f"{V}/lands/{land['id']}/transfers", headers=a, json={"new_owner_npi": "2222222222", "reason": "vente"}).status_code == 409
    assert client.get(f"{V}/lands/transfers/me", headers=b).json()[0]["id"] == t["id"]
    assert client.patch(f"{V}/lands/transfers/{t['id']}", headers=a, json={"status": "approuve"}).status_code == 403
    assert client.patch(f"{V}/lands/transfers/{t['id']}", headers=agent, json={"status": "approuve", "note": "Acte vérifié"}).json()["status"] == "approuve"
    moved = client.get(f"{V}/lands/{land['id']}", headers=b).json()
    assert moved["npi_owner"] == "2222222222" and moved["ownership_history"][0]["from_npi"] == "1111111111"
    assert client.get(f"{V}/lands/{land['id']}", headers=a).status_code == 403
    assert client.patch(f"{V}/lands/transfers/{t['id']}", headers=agent, json={"status": "rejete"}).status_code == 409


def test_transfer_cancel(client):
    a = login(client, "1111111111")
    land = create_land(client, a)
    t = client.post(f"{V}/lands/{land['id']}/transfers", headers=a, json={"new_owner_npi": "2222222222", "reason": "heritage"}).json()
    assert client.delete(f"{V}/lands/{land['id']}", headers=a).status_code == 409
    assert client.patch(f"{V}/lands/transfers/{t['id']}", headers=a, json={"status": "annule"}).json()["status"] == "annule"
    assert client.delete(f"{V}/lands/{land['id']}", headers=a).status_code == 204


def test_harvests(client):
    a = login(client, "1111111111")
    land = create_land(client, a)
    r = client.post(f"{V}/lands/{land['id']}/harvests", headers=a, json={"season": "2026-A", "actual_yield_kg": 7000, "harvest_date": "2026-08-15"})
    assert r.status_code == 201 and r.json()["yield_kg_per_ha"] > 6000
    assert client.post(f"{V}/lands/{land['id']}/harvests", headers=a, json={"season": "2026-A", "actual_yield_kg": 1}).status_code == 409
    assert client.post(f"{V}/lands/{land['id']}/harvests", headers=a, json={"season": "saison", "actual_yield_kg": 1}).status_code == 422
