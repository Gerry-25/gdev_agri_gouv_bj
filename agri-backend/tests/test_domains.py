from datetime import datetime, timedelta, timezone

from bson import ObjectId

from tests.conftest import (
    V, create_land, domain_payload, land_payload, login, make_agent, make_eligible_farmer, make_supervisor, run, square,
)

NOW = datetime.now(timezone.utc)


def call_payload(**kw):
    return {"title": "Mise en valeur de la ferme domaniale", "description": "Terre de l'État destinée au maïs.",
            "cahier_des_charges": "Mettre en valeur au moins 80 % de la surface dans les 12 mois. Pratiques durables.",
            "allowed_crops": ["Maïs", "Manioc"], "contract_type": "concession", "duration_years": 5,
            "annual_fee_fcfa_per_ha": 10000, "mise_en_valeur_months": 12, "min_score": 40,
            "opens_at": NOW.isoformat(), "closes_at": (NOW + timedelta(days=20)).isoformat(), **kw}


def shift(db, coll, oid, **fields):
    run(db[coll].update_one({"_id": ObjectId(oid)}, {"$set": fields}))


def setup_call(client, db):
    agent, sup1, sup2 = make_agent(client, db), make_supervisor(client, db), make_supervisor(client, db, "7777777777", "0177777777")
    domain = client.post(f"{V}/domains", headers=agent, json=domain_payload(6.70, 2.45)).json()
    call = client.post(f"{V}/domains/{domain['id']}/calls", headers=agent, json=call_payload()).json()
    assert client.post(f"{V}/calls/{call['id']}/publish", headers=sup1).status_code == 200
    return agent, sup1, sup2, domain, call


def test_domain_registration_and_overlaps(client, db):
    agent = make_agent(client, db)
    farmer = login(client, "1111111111")
    assert client.post(f"{V}/domains", headers=farmer, json=domain_payload(6.70, 2.45)).status_code == 403
    land = create_land(client, farmer, 6.7010, 2.4510)  # à l'intérieur de la future terre
    r = client.post(f"{V}/domains", headers=agent, json=domain_payload(6.70, 2.45))
    assert r.status_code == 201 and r.json()["status"] == "registered_with_dispute", r.text
    assert 8 < r.json()["surface_hectares"] < 12
    dom = client.get(f"{V}/domains/{r.json()['id']}", headers=agent).json()
    assert dom["dispute_flag"] and client.get(f"{V}/lands/{land['id']}", headers=farmer).json()["dispute_flag"]
    assert client.post(f"{V}/domains", headers=agent, json=domain_payload(6.701, 2.451)).status_code == 409, "chevauche une autre terre de l'État"

    # Une nouvelle parcelle privée sur la terre de l'État ouvre aussi un litige
    other = login(client, "2222222222", phone="0162000000")
    res = client.post(f"{V}/lands/", headers=other, json=land_payload(square(6.7015, 2.4520))).json()
    assert any(o.get("domain_id") for o in res["overlaps"])

    # Clôture des litiges : la terre redevient publiable
    for d in client.get(f"{V}/lands/disputes?status=ouvert", headers=agent).json():
        client.patch(f"{V}/lands/disputes/{d['id']}", headers=agent, json={"status": "resolu", "resolution_note": "Bornage refait"})
    assert client.get(f"{V}/domains/{dom['id']}", headers=agent).json()["dispute_flag"] is False
    assert len(client.get(f"{V}/domains/geojson", headers=agent).json()["features"]) == 1


def test_publication_rules(client, db):
    agent, sup = make_agent(client, db), make_supervisor(client, db)
    domain = client.post(f"{V}/domains", headers=agent, json=domain_payload(6.70, 2.45)).json()
    short = client.post(f"{V}/domains/{domain['id']}/calls", headers=agent,
                        json=call_payload(closes_at=(NOW + timedelta(days=5)).isoformat())).json()
    assert client.post(f"{V}/calls/{short['id']}/publish", headers=agent).status_code == 403, "un agent ne publie pas"
    assert client.post(f"{V}/calls/{short['id']}/publish", headers=sup).status_code == 422, "publicité trop courte"
    assert client.post(f"{V}/domains/{domain['id']}/calls", headers=agent, json=call_payload()).status_code == 409, "un seul appel à la fois"
    assert client.get(f"{V}/calls/{short['id']}").status_code == 404, "brouillon invisible du public"

    # Un superviseur qui rédige ne peut pas publier lui-même
    client.post(f"{V}/calls/{short['id']}/cancel", headers=sup, json={"reason": "Durée de publicité insuffisante"})
    own = client.post(f"{V}/domains/{domain['id']}/calls", headers=sup, json=call_payload()).json()
    assert client.post(f"{V}/calls/{own['id']}/publish", headers=sup).status_code == 403


def test_full_procedure(client, db):
    winner, _ = make_eligible_farmer(client, db, "1111111111", "0161000001", 6.58, 2.55, yields=(20000, 21000))
    runner, _ = make_eligible_farmer(client, db, "2222222222", "0161000002", 6.59, 2.56, yields=(10000, 10500))
    make_eligible_farmer(client, db, "4444444444", "0161000004", 6.60, 2.57, yields=(10000, 9500))
    newbie = login(client, "3333333333", phone="0161000003")
    agent, sup1, sup2, domain, call = setup_call(client, db)
    cid = call["id"]

    notes = client.get(f"{V}/notifications/me", headers=winner).json()
    assert notes[0]["type"] == "call_published", "exploitants éligibles prévenus"
    assert client.get(f"{V}/notifications/me/unread-count", headers=newbie).json()["unread"] == 0

    pub = client.get(f"{V}/calls?phase=ouvert").json()
    assert len(pub) == 1 and "created_by" not in pub[0] and pub[0]["boundary"]["type"] == "Polygon"

    # Candidatures
    el = client.get(f"{V}/calls/{cid}/eligibility/me", headers=newbie).json()
    assert not el["eligible"] and el["reasons"]
    r = client.post(f"{V}/calls/{cid}/applications", headers=newbie, json={"proposed_crop": "Maïs", "planned_yield_kg": 20000, "motivation": "Je veux cultiver cette terre."})
    assert r.status_code == 403 and r.json()["detail"]["reasons"]
    app = {"proposed_crop": "Maïs", "planned_yield_kg": 25000, "motivation": "Dix ans d'expérience en culture de maïs."}
    assert client.post(f"{V}/calls/{cid}/applications", headers=winner, json={**app, "proposed_crop": "Coton"}).status_code == 422
    a1 = client.post(f"{V}/calls/{cid}/applications", headers=winner, json=app).json()
    assert client.post(f"{V}/calls/{cid}/applications", headers=winner, json=app).status_code == 409
    assert client.delete(f"{V}/calls/{cid}/applications/me", headers=winner).json()["status"] == "retiree"
    a1 = client.post(f"{V}/calls/{cid}/applications", headers=winner, json=app).json()
    a2 = client.post(f"{V}/calls/{cid}/applications", headers=runner, json=app).json()
    assert a1["score_at_submission"] > a2["score_at_submission"]
    assert client.get(f"{V}/calls/{cid}/manage", headers=agent).json()["applications_count"] == 2

    ranked = client.get(f"{V}/calls/{cid}/applications", headers=agent).json()
    assert [a["farmer_npi"] for a in ranked] == ["1111111111", "2222222222"] and ranked[0]["rank"] == 1

    # Proposition impossible avant la clôture
    proposal = {"application_id": a2["id"], "justification": "Proximité immédiate de la terre et logistique maîtrisée."}
    assert client.post(f"{V}/calls/{cid}/award-proposal", headers=agent, json=proposal).status_code == 409
    shift(db, "calls", cid, opens_at=NOW - timedelta(days=30), closes_at=NOW - timedelta(days=1))
    assert client.post(f"{V}/calls/{cid}/applications", headers=runner, json=app).status_code == 409, "appel clôturé"

    # Écart au classement tracé ; refus par le superviseur
    r = client.post(f"{V}/calls/{cid}/award-proposal", headers=agent, json=proposal).json()
    assert r["status"] == "attribution_proposee" and r["award"]["deviation_from_ranking"] is True
    assert client.post(f"{V}/calls/{cid}/award-decision", headers=sup1, json={"approve": False, "note": "Écart au classement non justifié"}).json()["status"] == "publie"

    # Principe des quatre yeux : le superviseur qui propose ne valide pas
    proposal = {"application_id": a1["id"], "justification": "Meilleur score et projet solide, conforme au cahier des charges."}
    client.post(f"{V}/calls/{cid}/award-proposal", headers=sup1, json=proposal)
    assert client.post(f"{V}/calls/{cid}/award-decision", headers=sup1, json={"approve": True, "note": "ok ok"}).status_code == 403
    r = client.post(f"{V}/calls/{cid}/award-decision", headers=sup2, json={"approve": True, "note": "Conforme"}).json()
    assert r["status"] == "attribue" and r["award"]["deviation_from_ranking"] is False and r["award"]["contest_until"]
    assert client.get(f"{V}/calls/{cid}").json()["awarded_to_name"] == "Test Exploitant"

    # Contestation par un candidat (pas par un tiers ni par le lauréat)
    assert client.post(f"{V}/calls/{cid}/contestations", headers=newbie, json={"reason": "Je conteste cette attribution injuste."}).status_code == 403
    assert client.post(f"{V}/calls/{cid}/contestations", headers=winner, json={"reason": "Je conteste ma propre attribution ???"}).status_code == 400
    ct = client.post(f"{V}/calls/{cid}/contestations", headers=runner, json={"reason": "Je réside à côté de la terre depuis 20 ans."}).json()

    # Acceptation → concession en attente d'acte
    acc = client.post(f"{V}/calls/{cid}/acceptance", headers=winner, json={"accept": True}).json()
    conc_id = acc["concession_id"]
    assert client.get(f"{V}/concessions/me", headers=winner).json()[0]["status"] == "en_attente_acte"
    act = {"act_ref": "ARR-2026-042", "act_date": NOW.date().isoformat(), "authority": "Préfecture de l'Ouémé"}
    assert client.post(f"{V}/concessions/{conc_id}/official-act", headers=agent, json=act).status_code == 409, "délai de contestation"

    shift(db, "calls", cid, **{"award.contest_until": NOW - timedelta(days=1)})
    assert client.post(f"{V}/concessions/{conc_id}/official-act", headers=agent, json=act).status_code == 409, "contestation ouverte"
    client.patch(f"{V}/contestations/{ct['id']}", headers=sup1, json={"decision": "rejetee", "note": "Critère de résidence absent du cahier des charges"})
    conc = client.post(f"{V}/concessions/{conc_id}/official-act", headers=agent, json=act).json()
    assert conc["status"] == "active" and conc["annual_fee_fcfa"] > 0
    assert client.get(f"{V}/domains/{domain['id']}", headers=agent).json()["status"] == "attribue"
    assert client.get(f"{V}/calls/{cid}").json()["status"] == "concede"
    assert client.get(f"{V}/calls/applications/me", headers=runner).json()[0]["status"] == "non_retenue"

    # Suivi : récolte, inspection, redevance
    rep = {"season": "2026-B", "crop_type": "Maïs", "area_cultivated_ha": 8, "actual_yield_kg": 22000}
    assert client.post(f"{V}/concessions/{conc_id}/reports", headers=runner, json=rep).status_code == 403
    assert client.post(f"{V}/concessions/{conc_id}/reports", headers=winner, json={**rep, "area_cultivated_ha": 500}).status_code == 422
    assert client.post(f"{V}/concessions/{conc_id}/reports", headers=winner, json=rep).status_code == 201
    client.post(f"{V}/concessions/{conc_id}/inspections", headers=agent, json={"mise_en_valeur_pct": 85, "compliant": True, "note": "Maïs bien levé"})
    c = client.post(f"{V}/concessions/{conc_id}/payments", headers=agent, json={"year": 2026, "amount_fcfa": conc["annual_fee_fcfa"], "receipt_ref": "Q-001"}).json()
    assert c["balance_fcfa"] == 0 and c["latest_mise_en_valeur_pct"] == 85
    assert client.post(f"{V}/concessions/{conc_id}/payments", headers=agent, json={"year": 2026, "amount_fcfa": 1, "receipt_ref": "Q-001"}).status_code == 409
    detail = client.get(f"{V}/concessions/{conc_id}", headers=winner).json()
    assert len(detail["reports"]) == 1 and len(detail["inspections"]) == 1
    assert client.get(f"{V}/concessions/{conc_id}", headers=runner).status_code == 403

    # Tableau de bord
    m = client.get(f"{V}/state/dashboard-metrics", headers=agent).json()
    assert m["concessions_active"] == 1 and m["state_domains_attributed"] == 1 and m["concession_fees_collected_fcfa"] == conc["annual_fee_fcfa"]

    # Retrait par un superviseur uniquement
    term = {"status": "retiree", "reason": "defaut_mise_en_valeur", "note": "Terre abandonnée"}
    assert client.post(f"{V}/concessions/{conc_id}/termination", headers=agent, json=term).status_code == 403
    assert client.post(f"{V}/concessions/{conc_id}/termination", headers=sup1, json=term).json()["status"] == "retiree"
    assert client.get(f"{V}/domains/{domain['id']}", headers=agent).json()["status"] == "disponible"


def test_founded_contestation_cancels_award(client, db):
    winner, _ = make_eligible_farmer(client, db, "1111111111", "0161000001", 6.58, 2.55)
    runner, _ = make_eligible_farmer(client, db, "2222222222", "0161000002", 6.59, 2.56)
    agent, sup1, sup2, domain, call = setup_call(client, db)
    app = {"proposed_crop": "Maïs", "planned_yield_kg": 25000, "motivation": "Expérience solide en culture du maïs."}
    a1 = client.post(f"{V}/calls/{call['id']}/applications", headers=winner, json=app).json()
    client.post(f"{V}/calls/{call['id']}/applications", headers=runner, json=app)
    shift(db, "calls", call["id"], opens_at=NOW - timedelta(days=30), closes_at=NOW - timedelta(days=1))
    client.post(f"{V}/calls/{call['id']}/award-proposal", headers=agent, json={"application_id": a1["id"], "justification": "Meilleur classement de l'appel."})
    client.post(f"{V}/calls/{call['id']}/award-decision", headers=sup1, json={"approve": True, "note": "Conforme"})
    client.post(f"{V}/calls/{call['id']}/acceptance", headers=winner, json={"accept": True})
    ct = client.post(f"{V}/calls/{call['id']}/contestations", headers=runner, json={"reason": "Le lauréat a une parcelle non déclarée en litige."}).json()
    client.patch(f"{V}/contestations/{ct['id']}", headers=sup2, json={"decision": "fondee", "note": "Litige confirmé par l'ANDF"})
    c = client.get(f"{V}/calls/{call['id']}/manage", headers=agent).json()
    assert c["status"] == "publie" and c["phase"] == "cloture" and c["award"] is None
    assert client.get(f"{V}/concessions/me", headers=winner).json()[0]["status"] == "annulee"
    assert any(n["title"] == "Attribution annulée" for n in client.get(f"{V}/notifications/me", headers=winner).json())


def test_decline_and_lapsed_acceptance(client, db):
    first, _ = make_eligible_farmer(client, db, "1111111111", "0161000001", 6.58, 2.55)
    second, _ = make_eligible_farmer(client, db, "2222222222", "0161000002", 6.59, 2.56)
    agent, sup1, _, domain, call = setup_call(client, db)
    cid = call["id"]
    app = {"proposed_crop": "Maïs", "planned_yield_kg": 25000, "motivation": "Expérience solide en culture du maïs."}
    a1 = client.post(f"{V}/calls/{cid}/applications", headers=first, json=app).json()
    a2 = client.post(f"{V}/calls/{cid}/applications", headers=second, json=app).json()
    shift(db, "calls", cid, opens_at=NOW - timedelta(days=30), closes_at=NOW - timedelta(days=1))

    def award(app_id):
        client.post(f"{V}/calls/{cid}/award-proposal", headers=agent, json={"application_id": app_id, "justification": "Candidat suivant dans le classement."})
        client.post(f"{V}/calls/{cid}/award-decision", headers=sup1, json={"approve": True, "note": "Conforme"})

    award(a1["id"])
    assert client.post(f"{V}/calls/{cid}/acceptance", headers=first, json={"accept": False}).json()["status"] == "desistement"
    assert client.post(f"{V}/calls/{cid}/award-proposal", headers=agent, json={"application_id": a1["id"], "justification": "Nouvelle tentative avec le premier."}).status_code == 409

    award(a2["id"])
    shift(db, "calls", cid, **{"award.acceptance_deadline": NOW - timedelta(days=1)})
    assert client.post(f"{V}/calls/{cid}/acceptance", headers=second, json={"accept": True}).status_code == 409
    # Plus aucun candidat recevable : l'appel est déclaré infructueux et la terre redevient disponible
    r = client.post(f"{V}/calls/{cid}/unsuccessful", headers=sup1, json={"reason": "Aucun lauréat n'a confirmé."})
    assert r.json()["status"] == "infructueux"
    assert client.get(f"{V}/calls/applications/me", headers=second).json()[0]["status"] == "desistement"
    assert client.get(f"{V}/domains/{domain['id']}", headers=agent).json()["status"] == "disponible"
    assert client.post(f"{V}/domains/{domain['id']}/calls", headers=agent, json=call_payload()).status_code == 201, "nouvel appel possible"
