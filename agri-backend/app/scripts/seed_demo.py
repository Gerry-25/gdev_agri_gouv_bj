"""Génère des données de démonstration réalistes réparties sur les 12 départements.

Usage (Docker) :
    docker compose exec api python -m app.scripts.seed_demo            # ajoute les données
    docker compose exec api python -m app.scripts.seed_demo --reset    # supprime puis régénère
    docker compose exec api python -m app.scripts.seed_demo --reset-only

Toutes les données créées portent is_demo=True et peuvent être supprimées sans toucher aux vraies.
Les coordonnées des communes sont approximatives (centre-ville) : suffisant pour une démonstration.
"""
import argparse
import asyncio
import math
import random
from datetime import timedelta

from motor.motor_asyncio import AsyncIOMotorClient
from shapely.geometry import Polygon

from app.core import geo
from app.core.config import settings
from app.core.database import create_indexes
from app.core.utils import utcnow
from app.modules.knowledge.seed import seed_guides
from app.modules.monitoring.schemas import SEVERITY_COLORS

# (département, commune, latitude, longitude, cultures principales, côtière)
COMMUNES = [
    ("Ouémé", "Dangbo", 6.58, 2.55, ["Manioc", "Maïs", "Tomate"], False),
    ("Ouémé", "Adjohoun", 6.70, 2.49, ["Maïs", "Manioc", "Niébé"], False),
    ("Plateau", "Pobè", 6.98, 2.66, ["Manioc", "Maïs", "Palmier à huile"], False),
    ("Plateau", "Kétou", 7.36, 2.60, ["Maïs", "Manioc", "Igname"], False),
    ("Atlantique", "Allada", 6.67, 2.15, ["Ananas", "Maïs", "Manioc"], False),
    ("Atlantique", "Abomey-Calavi", 6.45, 2.35, ["Ananas", "Tomate", "Manioc"], False),
    ("Atlantique", "Ouidah", 6.37, 2.09, ["Maïs", "Manioc", "Tomate"], True),
    ("Littoral", "Cotonou", 6.37, 2.43, ["Tomate"], True),
    ("Mono", "Lokossa", 6.64, 1.72, ["Maïs", "Manioc", "Tomate"], False),
    ("Mono", "Grand-Popo", 6.29, 1.82, ["Tomate", "Manioc"], True),
    ("Couffo", "Aplahoué", 6.93, 1.68, ["Maïs", "Manioc", "Niébé"], False),
    ("Zou", "Bohicon", 7.18, 2.07, ["Maïs", "Niébé", "Manioc"], False),
    ("Zou", "Covè", 7.22, 2.34, ["Maïs", "Riz", "Manioc"], False),
    ("Collines", "Savalou", 7.93, 1.98, ["Igname", "Maïs", "Soja"], False),
    ("Collines", "Glazoué", 7.97, 2.24, ["Soja", "Maïs", "Igname"], False),
    ("Borgou", "Parakou", 9.34, 2.63, ["Maïs", "Igname", "Soja"], False),
    ("Borgou", "Nikki", 9.94, 3.21, ["Coton", "Maïs", "Igname"], False),
    ("Alibori", "Banikoara", 11.30, 2.44, ["Coton", "Maïs", "Sorgho"], False),
    ("Alibori", "Malanville", 11.87, 3.39, ["Riz", "Oignon", "Maïs"], False),
    ("Atacora", "Natitingou", 10.30, 1.38, ["Sorgho", "Maïs", "Igname"], False),
    ("Atacora", "Tanguiéta", 10.62, 1.26, ["Sorgho", "Coton", "Maïs"], False),
    ("Donga", "Djougou", 9.71, 1.67, ["Igname", "Maïs", "Soja"], False),
]

# Rendement (kg/ha) et prix (FCFA/kg) indicatifs pour la démonstration
CROPS = {
    "Maïs": ((1800, 3000), (200, 300)), "Manioc": ((10000, 20000), (60, 120)), "Ananas": ((40000, 60000), (150, 300)),
    "Tomate": ((8000, 15000), (300, 600)), "Igname": ((10000, 15000), (250, 400)), "Coton": ((900, 1400), (250, 300)),
    "Soja": ((900, 1400), (250, 350)), "Riz": ((3000, 4500), (200, 280)), "Sorgho": ((800, 1300), (180, 250)),
    "Niébé": ((600, 1000), (400, 600)), "Oignon": ((15000, 25000), (200, 400)), "Palmier à huile": ((5000, 9000), (80, 150)),
}

PESTS = {
    "Maïs": ["Chenille légionnaire d'automne", "Striure du maïs"],
    "Manioc": ["Mosaïque du manioc", "Cochenille farineuse du manioc"],
    "Tomate": ["Flétrissement bactérien", "Mouche blanche"],
    "Ananas": ["Wilt de l'ananas (cochenilles)"],
    "Coton": ["Chenille de la capsule", "Jassides"],
    "Igname": ["Mosaïque de l'igname"],
    "Niébé": ["Pucerons du niébé"],
    "Riz": ["Pyriculariose du riz"],
    "Sorgho": ["Moisissure des grains"],
    "Soja": ["Rouille du soja"],
    "Oignon": ["Thrips de l'oignon"],
    "Palmier à huile": ["Fusariose du palmier"],
}

# Foyers volontaires pour rendre la carte sanitaire parlante
HOTSPOTS = [("Dangbo", "Maïs", "Chenille légionnaire d'automne", 9),
            ("Banikoara", "Coton", "Chenille de la capsule", 7),
            ("Pobè", "Manioc", "Mosaïque du manioc", 5)]

FIRST = ["Koffi", "Awa", "Sèna", "Codjo", "Adjoa", "Bio", "Yaya", "Mariam", "Rodrigue", "Fifamè", "Gbènou", "Chabi",
         "Rachidatou", "Kpèdétin", "Orou", "Nafissatou", "Houénou", "Akim", "Bernadette", "Ismaël"]
LAST = ["Houngbo", "Dossou", "Adjovi", "Agossou", "Soglo", "Bio Tchané", "Sanni", "Gbaguidi", "Kiki", "Zinsou",
        "Ahouandjinou", "Tossou", "Orou Guéra", "Hounkpatin", "Akplogan", "Yarou", "Dansou", "Chabi Gani"]

DEMO_ACCOUNTS = [
    ("0100000001", "+2290190000001", "Démo Exploitant", "farmer"),
    ("0100000002", "+2290190000002", "Démo Acheteur", "buyer"),
    ("0100000003", "+2290190000003", "Démo Agent État", "state_agent"),
]

COLLECTIONS = ["users", "lands", "disputes", "transfers", "harvests", "market_offers", "offer_interests",
               "phytosanitary_alerts", "notifications"]


def _random_polygon(rng: random.Random, lat0: float, lon0: float, area_m2: float) -> Polygon:
    """Polygone irrégulier en étoile (toujours valide) d'environ area_m2 autour du point."""
    r = math.sqrt(area_m2 / math.pi)
    n = rng.randint(6, 10)
    step = 2 * math.pi / n
    # Angles répartis régulièrement avec un léger décalage : jamais deux sommets confondus
    angles = [i * step + rng.uniform(-0.3, 0.3) * step for i in range(n)]
    pts = []
    for a in angles:
        d = r * rng.uniform(0.75, 1.25)
        pts.append((lon0 + d * math.cos(a) / (111_320 * math.cos(math.radians(lat0))), lat0 + d * math.sin(a) / 110_540))
    return geo.build_polygon(pts)


def _offset(rng, lat, lon, max_km, north_only):
    dy = rng.uniform(0.3 if north_only else -1, 1) * max_km * 1000
    dx = rng.uniform(-1, 1) * max_km * 1000
    return lat + dy / 110_540, lon + dx / (111_320 * math.cos(math.radians(lat)))


async def reset_demo(db) -> dict:
    return {c: (await db[c].delete_many({"is_demo": True})).deleted_count for c in COLLECTIONS}


async def seed_demo(db, farmers: int = 80, seed: int = 229) -> dict:
    rng = random.Random(seed)
    now = utcnow()
    counts = dict.fromkeys(COLLECTIONS, 0)

    # --- Utilisateurs
    users = [{"npi": n, "phone": p, "full_name": name, "role": role, "preferred_language": "fr", "is_demo": True, "created_at": now}
             for n, p, name, role in DEMO_ACCOUNTS]
    for i in range(farmers):
        users.append({"npi": f"01{10000000 + i:08d}", "phone": f"+22901{60000000 + i:08d}",
                      "full_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}", "role": "farmer",
                      "preferred_language": rng.choice(["fr", "fr", "fr", "fon", "yo"]), "is_demo": True,
                      "created_at": now - timedelta(days=rng.randint(10, 300))})
    for i in range(15):
        users.append({"npi": f"02{10000000 + i:08d}", "phone": f"+22901{70000000 + i:08d}",
                      "full_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}", "role": "buyer", "preferred_language": "fr",
                      "is_demo": True, "created_at": now - timedelta(days=rng.randint(10, 300))})
    existing = set(await db["users"].distinct("npi", {"npi": {"$in": [u["npi"] for u in users]}}))
    new_users = [u for u in users if u["npi"] not in existing]
    if new_users:
        await db["users"].insert_many(new_users)
    counts["users"] = len(new_users)
    farmer_npis = [DEMO_ACCOUNTS[0][0]] + [u["npi"] for u in users if u["role"] == "farmer" and u["npi"] != DEMO_ACCOUNTS[0][0]]
    buyer_npis = [u["npi"] for u in users if u["role"] == "buyer"]
    agent_npi = DEMO_ACCOUNTS[2][0]

    # --- Parcelles (sans chevauchement, sauf quelques cas volontaires)
    lands, polys = [], []
    for idx, npi in enumerate(farmer_npis):
        home = COMMUNES[idx % len(COMMUNES)] if idx else COMMUNES[0]  # le compte démo est à Dangbo
        for _ in range(rng.randint(1, 4)):
            dept, commune, lat, lon, crops, coastal = home
            for _attempt in range(20):
                clat, clon = _offset(rng, lat, lon, 6, coastal)
                try:
                    poly = _random_polygon(rng, clat, clon, rng.uniform(3_000, 50_000))
                except geo.GeometryError:
                    continue
                if not any(poly.intersects(p) for p in polys):
                    break
            else:
                continue
            polys.append(poly)
            crop = rng.choice(crops)
            area = geo.area_m2(poly)
            yield_range = CROPS[crop][0]
            created = now - timedelta(days=rng.randint(5, 200))
            lands.append({
                "npi_owner": npi, "department": dept, "commune": commune, "locality": None, "crop_type": crop,
                "estimated_yield_kg": round(area / 10_000 * rng.uniform(*yield_range)), "cadastral_reference": None,
                "boundary": geo.to_geojson(poly), "centroid": geo.to_geojson(geo.centroid_point(poly)),
                "surface_hectares": round(area / 10_000, 4), "perimeter_m": round(geo.perimeter_m(poly), 1),
                "points_count": len(poly.exterior.coords) - 1, "gps_accuracy_mean_m": round(rng.uniform(3, 9), 1),
                "capture_method": "gps_walk", "dispute_flag": False,
                "verification_status": rng.choices(["declaree", "verifiee", "rejetee"], [55, 42, 3])[0],
                "boundary_history": [], "ownership_history": [], "is_demo": True, "created_at": created, "updated_at": created,
            })
    res = await db["lands"].insert_many(lands)
    for land, oid in zip(lands, res.inserted_ids):
        land["_id"] = oid
    counts["lands"] = len(lands)

    # --- Litiges : quelques chevauchements volontaires
    disputes = []
    for land in rng.sample(lands, 6):
        other_npi = rng.choice([n for n in farmer_npis if n != land["npi_owner"]])
        base = geo.from_geojson(land["boundary"])
        shifted = Polygon([(x + 0.0004, y + 0.0002) for x, y in base.exterior.coords])
        overlap = round(geo.overlap_area_m2(base, shifted), 1)
        area = geo.area_m2(shifted)
        created = now - timedelta(days=rng.randint(1, 40))
        intruder = {**{k: v for k, v in land.items() if k != "_id"}, "npi_owner": other_npi, "boundary": geo.to_geojson(shifted),
                    "centroid": geo.to_geojson(geo.centroid_point(shifted)), "surface_hectares": round(area / 10_000, 4),
                    "dispute_flag": True, "verification_status": "declaree", "created_at": created, "updated_at": created}
        other_id = (await db["lands"].insert_one(intruder)).inserted_id
        counts["lands"] += 1
        await db["lands"].update_one({"_id": land["_id"]}, {"$set": {"dispute_flag": True}})
        status = rng.choice(["ouvert", "ouvert", "en_mediation"])
        disputes.append({
            "type": "chevauchement", "status": status, "land_ids": [str(other_id), str(land["_id"])],
            "parties_npi": [other_npi, land["npi_owner"]], "reported_by": "systeme",
            "reason": f"Chevauchement de {overlap} m² détecté automatiquement entre deux contours GPS.",
            "department": land["department"], "commune": land["commune"], "overlap_area_m2": overlap,
            "history": [{"status": "ouvert", "by": "systeme", "at": created}], "is_demo": True, "created_at": created, "updated_at": created,
        })
    await db["disputes"].insert_many(disputes)
    counts["disputes"] = len(disputes)

    # --- Transferts en attente
    transfers = []
    for land in rng.sample([l for l in lands if not l["dispute_flag"]], 3):
        created = now - timedelta(days=rng.randint(1, 15))
        transfers.append({"land_id": str(land["_id"]), "from_npi": land["npi_owner"],
                          "new_owner_npi": rng.choice([n for n in farmer_npis if n != land["npi_owner"]]),
                          "reason": rng.choice(["vente", "heritage", "donation"]), "note": None, "status": "en_attente",
                          "department": land["department"], "commune": land["commune"], "is_demo": True,
                          "created_at": created, "updated_at": created})
    await db["transfers"].insert_many(transfers)
    counts["transfers"] = len(transfers)

    # --- Récoltes réelles (saison précédente)
    harvests = []
    for land in lands:
        if rng.random() < 0.6:
            actual = round(land["estimated_yield_kg"] * rng.uniform(0.65, 1.1))
            harvests.append({"land_id": str(land["_id"]), "npi_owner": land["npi_owner"], "season": "2026-A",
                             "crop_type": land["crop_type"], "actual_yield_kg": actual, "harvest_date": "2026-08-15",
                             "department": land["department"], "commune": land["commune"],
                             "estimated_yield_kg": land["estimated_yield_kg"], "is_demo": True, "created_at": now})
    if harvests:
        await db["harvests"].insert_many(harvests)
    counts["harvests"] = len(harvests)

    # --- Diagnostics
    def alert(land, disease, severity, days_ago):
        observed = now - timedelta(days=days_ago, hours=rng.randint(0, 23))
        lon, lat = land["centroid"]["coordinates"]
        healthy = disease is None
        return {
            "crop_identified": land["crop_type"],
            "health_status": "Sain" if healthy else rng.choice(["Maladie", "Attaque parasitaire"]),
            "disease_name": disease, "severity": "Aucune" if healthy else severity,
            "symptoms": [] if healthy else ["Feuilles abîmées", "Plants affaiblis"],
            "simple_summary": "Votre plante est en bonne santé." if healthy else f"Votre {land['crop_type'].lower()} est atteint : {disease}.",
            "treatment_steps": [] if healthy else ["Arracher les plants très atteints", "Appliquer un extrait de neem le soir", "Surveiller chaque semaine"],
            "treatment_advice": "Continuez les bonnes pratiques." if healthy else "Traitement biologique recommandé ; consultez l'agent de vulgarisation.",
            "confidence_score": round(rng.uniform(0.6, 0.95), 2),
            "alert_color": SEVERITY_COLORS["Aucune" if healthy else severity],
            "farmer_npi": land["npi_owner"], "crop_hint": land["crop_type"], "language": "fr", "has_image": False,
            "land_id": str(land["_id"]), "department": land["department"], "commune": land["commune"],
            "location": {"type": "Point", "coordinates": [lon + rng.uniform(-0.0003, 0.0003), lat + rng.uniform(-0.0003, 0.0003)]},
            "is_demo": True, "observed_at": observed, "created_at": observed,
        }

    alerts = []
    for land in rng.sample(lands, min(len(lands), 150)):
        if rng.random() < 0.35:
            alerts.append(alert(land, None, "Aucune", rng.randint(0, 60)))
        else:
            alerts.append(alert(land, rng.choice(PESTS[land["crop_type"]]), rng.choices(["Faible", "Moyenne", "Critique"], [45, 40, 15])[0], rng.randint(0, 60)))
    for commune, crop, disease, cases in HOTSPOTS:
        zone = [l for l in lands if l["commune"] == commune] or lands
        for _ in range(cases):
            land = {**rng.choice(zone), "crop_type": crop}
            alerts.append(alert(land, disease, rng.choices(["Moyenne", "Critique"], [50, 50])[0], rng.randint(0, 20)))
    await db["phytosanitary_alerts"].insert_many(alerts)
    counts["phytosanitary_alerts"] = len(alerts)

    # --- Offres de marché
    offers = []
    for land in rng.sample(lands, min(len(lands), 130)):
        price_range = CROPS[land["crop_type"]][1]
        qty = max(50, round(land["estimated_yield_kg"] * rng.uniform(0.1, 0.5), -1))
        price = round(rng.uniform(*price_range), -1)
        status = rng.choices(["active", "sold", "withdrawn"], [65, 30, 5])[0]
        created = now - timedelta(days=rng.randint(0, 80))
        owner = next(u for u in users if u["npi"] == land["npi_owner"])
        offer = {"product_name": land["crop_type"], "quantity_kg": qty, "unit_price_fcfa": price, "contact_phone": owner["phone"],
                 "land_id": str(land["_id"]), "location_commune": land["commune"], "department": land["department"],
                 "farmer_npi": land["npi_owner"], "status": status, "interest_count": 0, "is_demo": True,
                 "created_at": created, "updated_at": created}
        if status == "sold":
            offer.update({"sold_quantity_kg": round(qty * rng.uniform(0.6, 1.0), -1), "sold_unit_price_fcfa": round(price * rng.uniform(0.9, 1.05), -1),
                          "sold_at": created + timedelta(days=rng.randint(1, 10))})
        offers.append(offer)
    res = await db["market_offers"].insert_many(offers)
    counts["market_offers"] = len(offers)

    interests = []
    for offer, oid in zip(offers, res.inserted_ids):
        if offer["status"] == "active":
            for buyer in rng.sample(buyer_npis, rng.randint(0, 3)):
                interests.append({"offer_id": str(oid), "buyer_npi": buyer, "message": None,
                                  "quantity_kg": round(offer["quantity_kg"] * rng.uniform(0.2, 1), -1),
                                  "is_demo": True, "created_at": offer["created_at"] + timedelta(days=1)})
    if interests:
        await db["offer_interests"].insert_many(interests)
        for oid in {i["offer_id"] for i in interests}:
            n = sum(1 for i in interests if i["offer_id"] == oid)
            await db["market_offers"].update_one({"_id": next(r for r in res.inserted_ids if str(r) == oid)}, {"$set": {"interest_count": n}})
    counts["offer_interests"] = len(interests)

    # --- Quelques notifications pour les comptes de démonstration
    notes = [
        {"npi": DEMO_ACCOUNTS[0][0], "type": "sanitary_alert", "title": "Alerte : Chenille légionnaire d'automne",
         "message": "9 cas signalés à Dangbo ces 30 derniers jours. Surveillez vos champs.", "pictogram": "bug"},
        {"npi": DEMO_ACCOUNTS[0][0], "type": "offer_interest", "title": "Un acheteur est intéressé",
         "message": "Démo Acheteur est intéressé(e) par votre offre.", "pictogram": "buyer"},
        {"npi": agent_npi, "type": "sanitary_alert", "title": "Alerte : Chenille de la capsule",
         "message": "7 cas signalés à Banikoara ces 30 derniers jours.", "pictogram": "bug"},
    ]
    await db["notifications"].insert_many([{**n, "data": {}, "read": False, "is_demo": True, "created_at": now} for n in notes])
    counts["notifications"] = len(notes)
    return counts


async def main(args) -> None:
    client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000, tz_aware=True)
    db = client[settings.DATABASE_NAME]
    try:
        await create_indexes(db)
        await seed_guides(db)
        if args.reset or args.reset_only:
            print("[*] Suppression des données de démonstration :", await reset_demo(db))
        if not args.reset_only:
            print("[*] Données créées :", await seed_demo(db, farmers=args.farmers, seed=args.seed))
            print("\nComptes de démonstration (code SMS affiché par l'API en mode simulation) :")
            for npi, phone, name, role in DEMO_ACCOUNTS:
                print(f"  {role:<12} NPI {npi}  téléphone {phone}  ({name})")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--farmers", type=int, default=80, help="Nombre d'exploitants générés (défaut : 80)")
    parser.add_argument("--seed", type=int, default=229, help="Graine aléatoire (mêmes données à chaque fois)")
    parser.add_argument("--reset", action="store_true", help="Supprimer les données de démo avant de régénérer")
    parser.add_argument("--reset-only", action="store_true", help="Supprimer les données de démo sans régénérer")
    asyncio.run(main(parser.parse_args()))
