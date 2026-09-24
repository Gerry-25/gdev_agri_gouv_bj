from tests.conftest import V, create_land, diagnose, land_payload, login, make_agent, square


def test_state_routes_require_agent(client, db):
    a = login(client, "1111111111")
    for path in ("dashboard-metrics", "stats/zones", "stats/crops", "sanitary/hotspots", "map/lands", "map/alerts"):
        assert client.get(f"{V}/state/{path}", headers=a).status_code == 403


def test_dashboard_and_stats(client, db, fake_ai):
    a, b = login(client, "1111111111"), login(client, "2222222222", phone="0162000000")
    agent = make_agent(client, db)
    land = create_land(client, a)
    client.post(f"{V}/lands/", headers=b, json=land_payload(square(6.5805, 2.5495)))  # chevauchement -> litige
    client.post(f"{V}/lands/{land['id']}/harvests", headers=a, json={"season": "2026-A", "actual_yield_kg": 7000})
    for _ in range(3):
        diagnose(client, a, land_id=land["id"])
    o = client.post(f"{V}/market/offers", headers=a, json={"product_name": "Manioc", "quantity_kg": 1000, "unit_price_fcfa": 150,
                                                           "contact_phone": "0161000000", "land_id": land["id"]}).json()
    client.patch(f"{V}/market/offers/{o['id']}/status", headers=a, json={"status": "sold", "sold_quantity_kg": 800})

    m = client.get(f"{V}/state/dashboard-metrics", headers=agent).json()
    assert m["parcels_monitored"] == 2 and m["open_disputes"] == 1 and m["actual_production_kg"] == 7000
    assert m["market_sold_volume_fcfa"] == 120000 and m["revenue_from_declared_sales_fcfa"] == 1800
    assert m["registered_farmers"] == 2 and m["parcels_awaiting_verification"] == 2

    zone = client.get(f"{V}/state/stats/zones?level=commune", headers=agent).json()[0]
    assert zone["commune"] == "Dangbo" and zone["threats"] == 3 and zone["critical"] == 3 and zone["parcels_in_dispute"] == 2
    crops = client.get(f"{V}/state/stats/crops", headers=agent).json()
    assert crops[0]["crop_type"] == "Manioc" and crops[0]["actual_production_kg"] == 7000

    hot = client.get(f"{V}/state/sanitary/hotspots", headers=agent).json()["zones"][0]
    assert hot["is_hotspot"] and hot["alert_level"] == "red" and hot["affected_farmers"] == 1

    assert len(client.get(f"{V}/state/map/lands?dispute_only=true", headers=agent).json()["features"]) == 2
    alerts = client.get(f"{V}/state/map/alerts", headers=agent).json()["features"]
    assert len(alerts) == 3 and alerts[0]["geometry"]["type"] == "Point"
    assert client.get(f"{V}/state/map/lands?bbox=1,2,3", headers=agent).status_code == 422


def test_knowledge(client, db, fake_ai):
    a = login(client, "1111111111")
    agent = make_agent(client, db)
    cats = client.get(f"{V}/knowledge/categories").json()
    assert len(cats) == 5 and sum(c["count"] for c in cats) == 6
    assert len(client.get(f"{V}/knowledge/guides?category=bonnes_pratiques").json()) == 2
    assert len(client.get(f"{V}/knowledge/guides?q=neem").json()) == 1
    assert len(client.get(f"{V}/knowledge/guides?verified_only=true").json()) == 1
    g = {"slug": "stockage-grains", "title": "Bien stocker ses grains", "category": "bonnes_pratiques",
         "summary": "Séchez bien les grains avant de les stocker.", "source": "INRAB"}
    assert client.post(f"{V}/knowledge/guides", headers=a, json=g).status_code == 403
    assert client.post(f"{V}/knowledge/guides", headers=agent, json=g).status_code == 201
    assert client.post(f"{V}/knowledge/guides", headers=agent, json=g).status_code == 409
    upd = {k: v for k, v in g.items() if k != "slug"} | {"verified": True}
    assert client.put(f"{V}/knowledge/guides/stockage-grains", headers=agent, json=upd).json()["verified"]
    assert client.get(f"{V}/knowledge/guides/stockage-grains/audio", headers=a).headers["content-type"] == "audio/mpeg"
    assert client.delete(f"{V}/knowledge/guides/stockage-grains", headers=agent).status_code == 204


def test_notifications_read(client, db):
    a, buyer = login(client, "1111111111"), login(client, "3333333333", phone="0163000000", role="buyer")
    land = create_land(client, a)
    client.post(f"{V}/lands/{land['id']}/disputes", headers=buyer, json={"type": "limite", "reason": "La borne a été déplacée"})
    note = client.get(f"{V}/notifications/me?unread_only=true", headers=a).json()[0]
    assert client.patch(f"{V}/notifications/{note['id']}/read", headers=buyer).status_code == 404
    assert client.patch(f"{V}/notifications/{note['id']}/read", headers=a).json()["read"] is True
    assert client.post(f"{V}/notifications/me/read-all", headers=a).json()["updated"] == 0


def test_health(client):
    r = client.get("/health")
    assert r.status_code in (200, 503)
