from tests.conftest import V, create_land, login, make_agent, run

OFFER = {"product_name": "Manioc frais", "quantity_kg": 1000, "unit_price_fcfa": 150, "contact_phone": "0161000000"}


def test_publish_with_land_and_contact_links(client):
    a, b = login(client, "1111111111"), login(client, "2222222222", phone="0162000000")
    land = create_land(client, a)
    o = client.post(f"{V}/market/offers", headers=a, json={**OFFER, "land_id": land["id"]}).json()
    assert o["location_commune"] == "Dangbo" and o["department"] == "Ouémé"
    assert o["tel_url"] == "tel:+2290161000000" and o["whatsapp_url"].startswith("https://wa.me/2290161000000?text=")
    assert client.post(f"{V}/market/offers", headers=b, json={**OFFER, "land_id": land["id"]}).status_code == 403
    assert client.post(f"{V}/market/offers", headers=a, json=OFFER).status_code == 422, "localisation requise"
    assert client.post(f"{V}/market/offers", headers=a, json={**OFFER, "location_commune": "Allada", "unit_price_fcfa": -5}).status_code == 422


def test_buyer_cannot_publish(client):
    buyer = login(client, "3333333333", phone="0163000000", role="buyer")
    assert client.post(f"{V}/market/offers", headers=buyer, json={**OFFER, "location_commune": "Allada"}).status_code == 403


def test_status_lifecycle(client):
    a = login(client, "1111111111")
    o = client.post(f"{V}/market/offers", headers=a, json={**OFFER, "location_commune": "Allada"}).json()
    url = f"{V}/market/offers/{o['id']}"
    assert client.patch(f"{url}/status", headers=a, json={"status": "sold", "sold_quantity_kg": 2000}).status_code == 422
    assert client.patch(f"{url}/status", headers=a, json={"status": "withdrawn"}).json()["status"] == "withdrawn"
    assert client.get(url).status_code == 404, "offre retirée invisible du public"
    assert client.patch(f"{url}/status", headers=a, json={"status": "active"}).json()["status"] == "active"
    assert client.patch(f"{url}/status", headers=a, json={"status": "sold", "sold_quantity_kg": 800}).json()["sold_quantity_kg"] == 800
    assert client.patch(f"{url}/status", headers=a, json={"status": "active"}).status_code == 409
    assert client.patch(url, headers=a, json={"quantity_kg": 5}).status_code == 409
    assert len(client.get(f"{V}/market/offers/me", headers=a).json()) == 1


def test_catalogue_filters(client):
    a = login(client, "1111111111")
    client.post(f"{V}/market/offers", headers=a, json={**OFFER, "location_commune": "Allada"})
    client.post(f"{V}/market/offers", headers=a, json={**OFFER, "product_name": "Ananas", "location_commune": "Allada", "unit_price_fcfa": 300})
    assert len(client.get(f"{V}/market/offers?commune=allada").json()) == 2
    assert len(client.get(f"{V}/market/offers?product=ananas").json()) == 1
    assert len(client.get(f"{V}/market/offers?max_price=200").json()) == 1


def test_offer_idempotency(client, db):
    a = login(client, "1111111111")
    body = {**OFFER, "location_commune": "Allada", "client_ref": "offline-offer-0001"}
    first, again = client.post(f"{V}/market/offers", headers=a, json=body), client.post(f"{V}/market/offers", headers=a, json=body)
    assert first.status_code == 201 and again.status_code == 200 and first.json()["id"] == again.json()["id"]
    assert run(db.market_offers.count_documents({})) == 1


def test_interest_notifies_farmer(client):
    a = login(client, "1111111111")
    buyer = login(client, "3333333333", phone="0163000000", role="buyer", full_name="Kofi Acheteur")
    o = client.post(f"{V}/market/offers", headers=a, json={**OFFER, "location_commune": "Allada"}).json()
    url = f"{V}/market/offers/{o['id']}"
    assert client.post(f"{url}/interest", headers=a, json={}).status_code == 400
    assert client.post(f"{url}/interest", headers=buyer, json={"quantity_kg": 500}).status_code == 201
    assert client.post(f"{url}/interest", headers=buyer, json={}).status_code == 200, "pas de doublon"
    assert client.get(url).json()["interest_count"] == 1
    interests = client.get(f"{url}/interests", headers=a).json()
    assert interests[0]["buyer_name"] == "Kofi Acheteur" and interests[0]["buyer_phone"] == "+2290163000000"
    assert client.get(f"{url}/interests", headers=buyer).status_code == 403
    note = client.get(f"{V}/notifications/me", headers=a).json()[0]
    assert note["type"] == "offer_interest" and "500" in note["message"]


def test_reference_prices(client):
    a = login(client, "1111111111")
    for price in (100, 200):
        client.post(f"{V}/market/offers", headers=a, json={**OFFER, "location_commune": "Allada", "department": "Atlantique", "unit_price_fcfa": price})
    o = client.post(f"{V}/market/offers", headers=a, json={**OFFER, "location_commune": "Allada", "department": "Atlantique"}).json()
    client.patch(f"{V}/market/offers/{o['id']}/status", headers=a, json={"status": "sold", "sold_unit_price_fcfa": 180})
    p = client.get(f"{V}/market/prices?product=manioc").json()["prices"][0]
    assert p["offered"]["avg"] == 150 and p["offered"]["count"] == 2 and p["sold"]["avg"] == 180
