from app.core import geo
from app.scripts.seed_demo import DEMO_ACCOUNTS, reset_demo, seed_demo
from tests.conftest import V, login, run


def test_demo_seed_and_reset(client, db):
    counts = run(seed_demo(db, farmers=60))
    assert counts["lands"] > 40 and counts["phytosanitary_alerts"] > 50 and counts["disputes"] == 6
    lands = run(_all(db.lands))
    assert all(geo.in_benin(*l["centroid"]["coordinates"]) for l in lands)
    assert all(geo.from_geojson(l["boundary"]).is_valid for l in lands)

    npi, phone, _, _ = DEMO_ACCOUNTS[2]
    agent = login(client, npi, phone=phone)
    m = client.get(f"{V}/state/dashboard-metrics", headers=agent).json()
    assert m["parcels_monitored"] == counts["lands"] and m["open_disputes"] == 6 and m["pending_transfers"] == 3
    hot = client.get(f"{V}/state/sanitary/hotspots", headers=agent).json()["zones"]
    assert any(z["commune"] == "Dangbo" and z["is_hotspot"] for z in hot)

    farmer = login(client, DEMO_ACCOUNTS[0][0], phone=DEMO_ACCOUNTS[0][1])
    assert len(client.get(f"{V}/lands/me", headers=farmer).json()) >= 1

    # Domaine de l'État : un appel ouvert auquel le compte démo peut candidater
    perf = client.get(f"{V}/performance/me", headers=farmer).json()
    assert perf["eligible"], perf
    open_calls = client.get(f"{V}/calls?phase=ouvert").json()
    assert len(open_calls) == 1
    el = client.get(f"{V}/calls/{open_calls[0]['id']}/eligibility/me", headers=farmer).json()
    assert el["eligible"], el
    assert m["concessions_active"] == 1 and m["state_domains_total"] == 5
    closed = client.get(f"{V}/calls?phase=cloture").json()[0]
    assert len(client.get(f"{V}/calls/{closed['id']}/applications", headers=agent).json()) == 4

    assert run(seed_demo(db, farmers=60))["users"] == 0, "relancer ne duplique pas les comptes"
    run(reset_demo(db))
    assert run(db.lands.count_documents({})) == 0 and run(db.users.count_documents({"is_demo": True})) == 0
    assert run(db.state_domains.count_documents({})) == 0 and run(db.calls.count_documents({})) == 0


async def _all(coll):
    return [d async for d in coll.find({})]
