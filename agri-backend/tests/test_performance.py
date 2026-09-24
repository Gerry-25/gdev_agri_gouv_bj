from bson import ObjectId

from tests.conftest import V, create_land, land_payload, login, make_agent, make_eligible_farmer, run, square


def test_new_farmer_is_not_eligible(client):
    h = login(client, "1111111111")
    s = client.get(f"{V}/performance/me", headers=h).json()
    assert s["eligible"] is False and "saisons" in s["ineligibility_reasons"][0]
    assert {c["key"] for c in s["components"]} == {"productivity", "accuracy", "regularity", "compliance", "market"}


def test_only_verified_parcels_count(client, db):
    h = login(client, "1111111111")
    land = create_land(client, h)
    for season in ("2025-A", "2026-A"):
        client.post(f"{V}/lands/{land['id']}/harvests", headers=h, json={"season": season, "actual_yield_kg": 50000})
    s = client.get(f"{V}/performance/me", headers=h).json()
    assert s["stats"]["harvests_counted"] == 0 and not s["eligible"], "récoltes sur parcelle non vérifiée ignorées"
    run(db.lands.update_one({"_id": ObjectId(land["id"])}, {"$set": {"verification_status": "verifiee"}}))
    s = client.get(f"{V}/performance/me", headers=h).json()
    assert s["stats"]["harvests_counted"] == 2 and s["eligible"]


def test_productivity_is_relative_to_peers(client, db):
    good, _ = make_eligible_farmer(client, db, "1111111111", "0161000001", 6.58, 2.55, yields=(20000, 21000))
    make_eligible_farmer(client, db, "2222222222", "0161000002", 6.59, 2.56, yields=(10000, 10500))
    make_eligible_farmer(client, db, "3333333333", "0161000003", 6.60, 2.57, yields=(10000, 9500))
    agent = make_agent(client, db)
    ranking = client.get(f"{V}/state/farmers/performance", headers=agent).json()
    assert ranking[0]["npi"] == "1111111111" and ranking[0]["rank"] == 1
    prod = next(c for c in ranking[0]["components"] if c["key"] == "productivity")
    assert prod["score"] > 90 and "médiane" in prod["detail"]
    assert client.get(f"{V}/state/farmers/performance", headers=good).status_code == 403
    assert len(client.get(f"{V}/state/farmers/performance?min_score=99", headers=agent).json()) == 0


def test_dispute_suspends_eligibility(client, db):
    h, land = make_eligible_farmer(client, db, "1111111111", "0161000001", 6.58, 2.55)
    assert client.get(f"{V}/performance/me", headers=h).json()["eligible"]
    other = login(client, "2222222222", phone="0162000000")
    client.post(f"{V}/lands/", headers=other, json=land_payload(square(6.5805, 2.5495)))
    s = client.get(f"{V}/performance/me", headers=h).json()
    assert not s["eligible"] and any("litige" in r for r in s["ineligibility_reasons"])
