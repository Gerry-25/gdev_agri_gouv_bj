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

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from shapely.geometry import Polygon

from app.core import geo
from app.core.config import settings
from app.core.database import create_indexes
from app.core.utils import utcnow
from app.modules.knowledge.seed import seed_guides
from app.modules.monitoring.schemas import SEVERITY_COLORS
from app.modules.performance.service import compute_scores

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
    ("0100000004", "+2290190000004", "Démo Superviseur État", "state_supervisor"),
]

COLLECTIONS = ["users", "lands", "disputes", "transfers", "harvests", "market_offers", "offer_interests",
               "phytosanitary_alerts", "notifications", "state_domains", "calls", "applications", "contestations",
               "concessions", "concession_reports", "concession_inspections", "stock_lots", "farmer_health_alerts",
               "financial_offers", "financial_applications"]
SEASONS = ["2025-A", "2025-B", "2026-A"]


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


STATE_DOMAINS = [
    # (commune index, nom, surface ha, étape)
    (0, "Ferme domaniale de Dangbo", 25, "appel_ouvert"),
    (15, "Périmètre agricole de Parakou - lot 3", 40, "appel_cloture"),
    (13, "Domaine agricole de Savalou", 30, "concession_active"),
    (17, "Ferme semencière de Banikoara", 20, "disponible"),
    (4, "Réserve foncière d'Allada", 15, "disponible"),
]


async def _seed_state_domains(db, rng, polys, farmer_npis, now) -> dict:
    counts = {k: 0 for k in ("state_domains", "calls", "applications", "concessions", "concession_reports", "concession_inspections")}
    agent, supervisor = DEMO_ACCOUNTS[2][0], DEMO_ACCOUNTS[3][0]
    scores = await compute_scores(db, farmer_npis)
    ranked = sorted((s for s in scores.values() if s["eligible"]), key=lambda s: -s["score"])

    for idx, name, hectares, stage in STATE_DOMAINS:
        dept, commune, lat, lon, crops, coastal = COMMUNES[idx]
        for _ in range(50):
            clat, clon = _offset(rng, lat, lon, 9, coastal)
            poly = _random_polygon(rng, clat, clon, hectares * 10_000)
            if not any(poly.intersects(p) for p in polys):
                break
        polys.append(poly)
        area = geo.area_m2(poly)
        created = now - timedelta(days=120)
        domain = {"name": name, "department": dept, "commune": commune, "locality": None, "land_title_ref": f"TF-DEMO-{idx:03d}",
                  "suitable_crops": crops, "description": "Terre du domaine privé de l'État (données de démonstration).",
                  "boundary": geo.to_geojson(poly), "centroid": geo.to_geojson(geo.centroid_point(poly)),
                  "surface_hectares": round(area / 10_000, 4), "perimeter_m": round(geo.perimeter_m(poly), 1),
                  "points_count": len(poly.exterior.coords) - 1, "gps_accuracy_mean_m": 2.0, "capture_method": "survey",
                  "status": "disponible", "dispute_flag": False, "current_call_id": None, "current_concession_id": None,
                  "created_by": agent, "is_demo": True, "created_at": created, "updated_at": created}
        if stage == "disponible" and idx == 17:
            # Terre prête pour la démonstration du plan de mise en valeur par l'IA
            domain["survey"] = {"survey_date": (now - timedelta(days=10)).date().isoformat(), "agroecological_zone": 2,
                                "land_use_history": "jachere", "fallow_years": 5, "last_crops": ["Coton", "Maïs"],
                                "water_sources": ["puits"], "irrigation_possible": False, "flooding_observed": "jamais",
                                "vegetation_cover": "arbustive", "trees_to_preserve": "Karité", "erosion": "legere",
                                "stoniness": "faible", "clearing_needed": "leger", "rainy_season_access": "bonne",
                                "infrastructures": ["magasin"], "labor_availability": "bonne", "surveyed_by": agent, "saved_at": now}
            domain["orientation"] = {"vocation": "semences", "priority_crops": ["Soja", "Maïs"], "excluded_crops": [],
                                     "investment_level": "moyen", "mechanization": "attelee", "min_valorization_pct": 80,
                                     "notes": "Production de semences certifiées pour la région.", "set_by": agent, "saved_at": now}
        domain_id = str((await db["state_domains"].insert_one(domain)).inserted_id)
        counts["state_domains"] += 1
        if stage == "disponible":
            continue

        closed = stage != "appel_ouvert"
        opens = now - timedelta(days=60 if closed else 5)
        closes = now - timedelta(days=10) if closed else now + timedelta(days=25)
        call = {"title": f"Appel à candidatures - {name}", "description": f"Mise en valeur de {round(area / 10_000)} ha du domaine privé de l'État.",
                "cahier_des_charges": "Mettre en valeur au moins 80 % de la surface dans les 12 mois suivant l'acte. "
                                      "Pratiques durables, rotation des cultures, déclaration des récoltes à chaque saison.",
                "allowed_crops": crops, "contract_type": "concession", "duration_years": 5, "annual_fee_fcfa_per_ha": 15000,
                "mise_en_valeur_months": 12, "min_score": 45, "eligible_departments": [], "opens_at": opens, "closes_at": closes,
                "domain_id": domain_id, "domain_name": name, "department": dept, "commune": commune,
                "surface_hectares": domain["surface_hectares"], "status": "publie", "applications_count": 0, "award": None,
                "created_by": agent, "published_by": supervisor, "published_at": opens,
                "history": [{"action": "creation", "by": agent, "note": None, "at": opens},
                            {"action": "publication", "by": supervisor, "note": None, "at": opens}],
                "is_demo": True, "created_at": opens, "updated_at": opens}
        call_id = str((await db["calls"].insert_one(call)).inserted_id)
        counts["calls"] += 1
        await db["state_domains"].update_one({"_id": ObjectId(domain_id)}, {"$set": {"status": "appel_en_cours", "current_call_id": call_id}})

        # Candidats : les mieux classés (hors compte démo, pour qu'il puisse candidater lui-même)
        candidates = [s for s in ranked if s["npi"] != DEMO_ACCOUNTS[0][0]][idx % 5: idx % 5 + (2 if stage == "appel_ouvert" else 4)]
        apps = []
        for c in candidates:
            apps.append({"proposed_crop": rng.choice(crops), "planned_yield_kg": round(hectares * CROPS[crops[0]][0][1]),
                         "motivation": "Exploitant expérimenté souhaitant étendre sa production sur une terre de l'État.",
                         "experience_years": rng.randint(3, 25), "call_id": call_id, "farmer_npi": c["npi"], "farmer_name": c["full_name"],
                         "score_at_submission": c["score"], "score_components": c["components"], "status": "deposee",
                         "is_demo": True, "created_at": opens + timedelta(days=2), "updated_at": opens + timedelta(days=2)})
        if apps:
            res = await db["applications"].insert_many(apps)
            await db["calls"].update_one({"_id": ObjectId(call_id)}, {"$set": {"applications_count": len(apps)}})
            counts["applications"] += len(apps)

        if stage == "concession_active" and apps:
            best = apps[0]
            start = now - timedelta(days=200)
            award = {"application_id": str(res.inserted_ids[0]), "farmer_npi": best["farmer_npi"], "farmer_name": best["farmer_name"],
                     "score": best["score_at_submission"], "proposed_by": agent, "proposed_at": closes, "justification": "Meilleur classement.",
                     "deviation_from_ranking": False, "approved_by": supervisor, "approved_at": closes,
                     "contest_until": closes, "acceptance_deadline": closes, "accepted_at": closes}
            fee = round(15000 * domain["surface_hectares"])
            conc = {"call_id": call_id, "domain_id": domain_id, "domain_name": name, "department": dept, "commune": commune,
                    "surface_hectares": domain["surface_hectares"], "farmer_npi": best["farmer_npi"], "farmer_name": best["farmer_name"],
                    "contract_type": "concession", "duration_years": 5, "crop_type": best["proposed_crop"],
                    "planned_yield_kg": best["planned_yield_kg"], "annual_fee_fcfa": fee, "mise_en_valeur_months": 12,
                    "cahier_des_charges": call["cahier_des_charges"], "status": "active", "act_ref": "ARR-DEMO-2026-001",
                    "act_date": start, "authority": f"Préfecture ({dept})", "start_date": start,
                    "end_date": start.replace(year=start.year + 5), "mise_en_valeur_deadline": start + timedelta(days=365),
                    "payments": [{"year": start.year, "amount_fcfa": fee, "receipt_ref": "Q-DEMO-001", "recorded_by": agent, "recorded_at": start}],
                    "latest_mise_en_valeur_pct": 70, "latest_compliant": True, "last_inspection_at": now - timedelta(days=30),
                    "history": [], "is_demo": True, "created_at": start, "updated_at": now}
            conc_id = str((await db["concessions"].insert_one(conc)).inserted_id)
            counts["concessions"] += 1
            await db["calls"].update_one({"_id": ObjectId(call_id)}, {"$set": {"status": "concede", "award": award, "concession_id": conc_id}})
            await db["applications"].update_one({"_id": res.inserted_ids[0]}, {"$set": {"status": "retenue"}})
            await db["applications"].update_many({"call_id": call_id, "status": "deposee"}, {"$set": {"status": "non_retenue"}})
            await db["state_domains"].update_one({"_id": ObjectId(domain_id)}, {"$set": {"status": "attribue", "current_call_id": None,
                                                                                         "current_concession_id": conc_id}})
            area_cult = round(domain["surface_hectares"] * 0.7, 2)
            await db["concession_reports"].insert_one({"season": "2026-A", "crop_type": best["proposed_crop"], "area_cultivated_ha": area_cult,
                                                       "actual_yield_kg": round(area_cult * CROPS[best["proposed_crop"]][0][1]),
                                                       "concession_id": conc_id, "farmer_npi": best["farmer_npi"], "department": dept,
                                                       "commune": commune, "expected_yield_kg": round(best["planned_yield_kg"] * 0.7),
                                                       "is_demo": True, "created_at": now - timedelta(days=60)})
            await db["concession_inspections"].insert_one({"mise_en_valeur_pct": 70, "compliant": True, "note": "Culture bien conduite.",
                                                           "concession_id": conc_id, "inspector_npi": agent, "is_demo": True,
                                                           "created_at": now - timedelta(days=30)})
            counts["concession_reports"] += 1
            counts["concession_inspections"] += 1
    return counts


async def _seed_farmer_health(db, rng, users, lands, now, agent_npi) -> int:
    """Génère des dossiers de santé réalistes (urgences, soins en cours, résolus) répartis sur le Bénin."""
    demo_farmer = DEMO_ACCOUNTS[0]
    farmer_users = [u for u in users if u.get("role") == "farmer" and u["npi"] != demo_farmer[0]]
    demo_land_id = str(lands[0]["_id"]) if lands else None

    health_alerts = [
        # 1. Exploitant démo : Morsure de serpent prise en charge
        {
            "npi": demo_farmer[0],
            "patient_name": demo_farmer[2],
            "patient_relation": "exploitant",
            "phone": demo_farmer[1],
            "department": "Ouémé",
            "commune": "Dangbo",
            "locality": "Zone de bas-fonds de Dangbo",
            "land_id": demo_land_id,
            "symptoms": "Morsure de serpent à la cheville droite lors du désherbage. Forte douleur brûlante, gonflement immédiat remontant vers le mollet.",
            "suspected_cause": "Reptile heurté sous les herbes de manioc",
            "work_related": True,
            "urgency_perceived": "vitale",
            "urgency_level": "vitale",
            "urgency_label": "Urgence vitale - Envenimation suspectée",
            "category": "morsure_piqure",
            "category_label": "Morsure de serpent ou piqûre venimeuse",
            "ai_recommendation": {
                "urgency_level": "vitale",
                "urgency_label": "Urgence vitale - Envenimation suspectée",
                "category": "morsure_piqure",
                "category_label": "Morsure de serpent ou piqûre venimeuse",
                "first_aid_steps": [
                    "Allonger immédiatement la victime au repos complet (l'agitation accélère la diffusion du venin).",
                    "Immobiliser la jambe atteinte avec une attelle ou une écharpe sans serrer, membre sous le niveau du cœur.",
                    "Retirer sans délai chaussures et bracelets avant l'installation du gonflement (œdème).",
                    "Nettoyer doucement à l'eau claire sans frotter et organiser le transport d'urgence."
                ],
                "things_to_avoid": [
                    "NE JAMAIS poser de garrot serré (risque majeur de nécrose et d'amputation).",
                    "NE JAMAIS inciser, sucer la plaie, ni brûler au niveau des points d'inoculation.",
                    "NE PAS appliquer de poudres traditionnelles, feuilles ou glace."
                ],
                "avoid": [
                    "NE JAMAIS poser de garrot serré (risque majeur de nécrose et d'amputation).",
                    "NE JAMAIS inciser, sucer la plaie, ni brûler au niveau des points d'inoculation.",
                    "NE PAS appliquer de poudres traditionnelles, feuilles ou glace."
                ],
                "medical_orientation": "Évacuation d'urgence immédiate vers l'Hôpital de Zone disposant de sérum antivenimeux.",
                "medical_referral": "Évacuation d'urgence immédiate vers l'Hôpital de Zone disposant de sérum antivenimeux.",
                "simple_summary": "Morsure de serpent suspectée : gardez la victime allongée et calme sans bouger la jambe. Ne faites ni garrot ni incision, et rejoignez l'hôpital pour l'antivenin."
            },
            "status": "pris_en_charge",
            "assigned_service": {
                "facility_name": "Hôpital de Zone Dangbo-Adjohoun-Bonou",
                "facility_type": "hopital_de_zone",
                "facility_phone": "+229 20 26 01 10",
                "department": "Ouémé",
                "commune": "Dangbo",
                "intervention_type": "evacuation_urgence",
                "instructions": "Équipe SAMU mobilisée avec sérum antivenimeux. Patient en cours de transfert.",
                "assigned_by": agent_npi,
                "assigned_at": now - timedelta(hours=2),
            },
            "resolution_notes": None,
            "is_demo": True,
            "created_at": now - timedelta(hours=3),
            "updated_at": now - timedelta(hours=2),
        },
        # 2. Exploitant démo : Coupure d'outil traitée et résolue
        {
            "npi": demo_farmer[0],
            "patient_name": demo_farmer[2],
            "patient_relation": "exploitant",
            "phone": demo_farmer[1],
            "department": "Ouémé",
            "commune": "Dangbo",
            "locality": "Hangar de stockage",
            "land_id": demo_land_id,
            "symptoms": "Plaie superficielle à la main droite causée par un éclat de tôle en réparant le hangar.",
            "suspected_cause": "Tôle rouillée",
            "work_related": True,
            "urgency_perceived": "faible",
            "urgency_level": "faible",
            "urgency_label": "Urgence faible - Soins locaux",
            "category": "traumatisme_agricole",
            "category_label": "Traumatisme et blessure agricole",
            "ai_recommendation": {
                "urgency_level": "faible",
                "urgency_label": "Urgence faible - Soins locaux",
                "category": "traumatisme_agricole",
                "category_label": "Traumatisme et blessure agricole",
                "first_aid_steps": [
                    "Nettoyer abondamment la plaie à l'eau courante et au savon neutre.",
                    "Appliquer un antiseptique local et couvrir avec une compresse propre.",
                    "Vérifier le carnet de vaccination contre le tétanos."
                ],
                "things_to_avoid": [
                    "NE PAS laisser la plaie souillée par la terre ou la poussière.",
                    "NE PAS appliquer de produits corrosifs ou poudres non désinfectées."
                ],
                "avoid": [
                    "NE PAS laisser la plaie souillée par la terre ou la poussière.",
                    "NE PAS appliquer de produits corrosifs ou poudres non désinfectées."
                ],
                "medical_orientation": "Consultation au Centre de Santé d'Arrondissement (CSA) Dangbo pour pansement et rappel antitétanique.",
                "medical_referral": "Consultation au Centre de Santé d'Arrondissement (CSA) Dangbo pour pansement et rappel antitétanique.",
                "simple_summary": "Plaie superficielle : nettoyez abondamment au savon propre, désinfectez et faites vérifier votre vaccin antitétanique au CSA."
            },
            "status": "resolu",
            "assigned_service": {
                "facility_name": "Centre de Santé d'Arrondissement (CSA) Dangbo",
                "facility_type": "centre_de_sante",
                "facility_phone": "+229 97 00 11 22",
                "department": "Ouémé",
                "commune": "Dangbo",
                "intervention_type": "soins_premiers_secours",
                "instructions": "Désinfection et vérification du rappel antitétanique.",
                "assigned_by": agent_npi,
                "assigned_at": now - timedelta(days=5),
            },
            "resolution_notes": "Suture légère et pansement effectués. Rappel antitétanique à jour. Cicatrisation complète.",
            "is_demo": True,
            "created_at": now - timedelta(days=6),
            "updated_at": now - timedelta(days=4),
        },
        # 3. Alibori / Banikoara : Intoxication pesticide coton (Signalé en attente -> urgence vitale cockpit)
        {
            "npi": farmer_users[0]["npi"] if len(farmer_users) > 0 else "0100000010",
            "patient_name": "Bio Chabi",
            "patient_relation": "ouvrier_agricole",
            "phone": "+229 97 45 12 34",
            "department": "Alibori",
            "commune": "Banikoara",
            "locality": "Zone cotonnière de Gomparou",
            "land_id": None,
            "symptoms": "Vertiges violents, nausées, vomissements répétés, hypersalivation et détresse respiratoire après pulvérisation de pesticides sur coton sans équipement de protection.",
            "suspected_cause": "Inhalation d'insecticide organophosphoré",
            "work_related": True,
            "urgency_perceived": "vitale",
            "urgency_level": "vitale",
            "urgency_label": "Urgence vitale - Intoxication chimique aiguë",
            "category": "intoxication_pesticide",
            "category_label": "Intoxication par produit phytosanitaire",
            "ai_recommendation": {
                "urgency_level": "vitale",
                "urgency_label": "Urgence vitale - Intoxication chimique aiguë",
                "category": "intoxication_pesticide",
                "category_label": "Intoxication par produit phytosanitaire",
                "first_aid_steps": [
                    "Éloigner immédiatement la victime du champ traité et retirer tous les vêtements contaminés.",
                    "Laver abondamment le corps et le visage à grande eau claire et au savon pendant 15 minutes.",
                    "Placer la victime en position latérale de sécurité (PLS) pour libérer les voies respiratoires.",
                    "Conserver l'étiquette ou le flacon du produit pour le médecin urgentiste."
                ],
                "things_to_avoid": [
                    "NE JAMAIS faire vomir (danger d'asphyxie et de brûlures caustiques).",
                    "NE PAS donner de lait, d'huile ou d'alcool (ils facilitent l'absorption intestinale).",
                    "NE PAS laisser la victime sans surveillance."
                ],
                "avoid": [
                    "NE JAMAIS faire vomir (danger d'asphyxie et de brûlures caustiques).",
                    "NE PAS donner de lait, d'huile ou d'alcool (ils facilitent l'absorption intestinale).",
                    "NE PAS laisser la victime sans surveillance."
                ],
                "medical_orientation": "Évacuation d'extrême urgence vers l'Hôpital de Zone de Kandi ou CSA Banikoara.",
                "medical_referral": "Évacuation d'extrême urgence vers l'Hôpital de Zone de Kandi ou CSA Banikoara.",
                "simple_summary": "Intoxication chimique sévère aux pesticides : lavez abondamment la peau, déshabillez la victime et ne faites surtout pas vomir. Transportez-la d'urgence à l'hôpital avec l'emballage du produit."
            },
            "status": "signale",
            "assigned_service": None,
            "resolution_notes": None,
            "is_demo": True,
            "created_at": now - timedelta(hours=1),
            "updated_at": now - timedelta(hours=1),
        },
        # 4. Atlantique / Allada : Plaie machette profonde (Prise en charge)
        {
            "npi": farmer_users[1]["npi"] if len(farmer_users) > 1 else "0100000011",
            "patient_name": "Codjo Agossou",
            "patient_relation": "exploitant",
            "phone": "+229 96 11 22 33",
            "department": "Atlantique",
            "commune": "Allada",
            "locality": "Plantation d'ananas de Tori",
            "land_id": None,
            "symptoms": "Coupure profonde à l'avant-bras gauche lors de la récolte d'ananas avec saignement abondant.",
            "suspected_cause": "Coupe-coupe affûté",
            "work_related": True,
            "urgency_perceived": "urgente",
            "urgency_level": "urgente",
            "urgency_label": "Urgence chirurgicale - Plaie hémorragique",
            "category": "traumatisme_agricole",
            "category_label": "Traumatisme et blessure agricole",
            "ai_recommendation": {
                "urgency_level": "urgente",
                "urgency_label": "Urgence chirurgicale - Plaie hémorragique",
                "category": "traumatisme_agricole",
                "category_label": "Traumatisme et blessure agricole",
                "first_aid_steps": [
                    "Comprimer fortement la plaie avec un tissu très propre pour arrêter le saignement.",
                    "Surélever le bras au-dessus du niveau du cœur tout en maintenant la pression.",
                    "Allonger le blessé pour éviter un malaise vagal."
                ],
                "things_to_avoid": [
                    "NE PAS relâcher la compression pour vérifier si le sang coule toujours.",
                    "NE PAS appliquer de sable, cendre ou café sur la plaie."
                ],
                "avoid": [
                    "NE PAS relâcher la compression pour vérifier si le sang coule toujours.",
                    "NE PAS appliquer de sable, cendre ou café sur la plaie."
                ],
                "medical_orientation": "Prise en charge au service des urgences du CHUD Atlantique (Allada).",
                "medical_referral": "Prise en charge au service des urgences du CHUD Atlantique (Allada).",
                "simple_summary": "Plaie profonde avec hémorragie : comprimez fortement la plaie avec un linge propre sans relâcher et surélevez le bras en rejoignant le CHUD Allada."
            },
            "status": "pris_en_charge",
            "assigned_service": {
                "facility_name": "CHUD Atlantique (Allada)",
                "facility_type": "hopital_de_zone",
                "facility_phone": "+229 21 39 01 44",
                "department": "Atlantique",
                "commune": "Allada",
                "intervention_type": "consultation",
                "instructions": "Prise en charge au bloc de petite chirurgie pour hémostase et suture.",
                "assigned_by": agent_npi,
                "assigned_at": now - timedelta(hours=4),
            },
            "resolution_notes": None,
            "is_demo": True,
            "created_at": now - timedelta(hours=5),
            "updated_at": now - timedelta(hours=4),
        },
        # 5. Alibori / Malanville : Coup de chaleur (En cours)
        {
            "npi": farmer_users[2]["npi"] if len(farmer_users) > 2 else "0100000012",
            "patient_name": "Yaya Sanni",
            "patient_relation": "exploitant",
            "phone": "+229 95 33 44 55",
            "department": "Alibori",
            "commune": "Malanville",
            "locality": "Périmètre rizicole du fleuve Niger",
            "land_id": None,
            "symptoms": "Malaise soudain, confusion, peau sèche et brûlante, crampes musculaires douloureuses après 7h sous le soleil.",
            "suspected_cause": "Canicule et manque d'hydratation",
            "work_related": True,
            "urgency_perceived": "moderee",
            "urgency_level": "moderee",
            "urgency_label": "Urgence modérée - Coup de chaleur",
            "category": "coup_chaleur_deshydratation",
            "category_label": "Coup de chaleur et déshydratation",
            "ai_recommendation": {
                "urgency_level": "moderee",
                "urgency_label": "Urgence modérée - Coup de chaleur",
                "category": "coup_chaleur_deshydratation",
                "category_label": "Coup de chaleur et déshydratation",
                "first_aid_steps": [
                    "Installer immédiatement le patient à l'ombre fraîche et bien aérée.",
                    "Mouiller le visage, le cou et le torse avec un linge frais humide.",
                    "Faire boire de petites gorgées d'eau fraîche légèrement salée s'il est conscient."
                ],
                "things_to_avoid": [
                    "NE PAS donner à boire s'il est somnolent ou désorienté (risque de fausse route).",
                    "NE PAS plonger brutalement dans de l'eau glacée (choc thermique)."
                ],
                "avoid": [
                    "NE PAS donner à boire s'il est somnolent ou désorienté (risque de fausse route).",
                    "NE PAS plonger brutalement dans de l'eau glacée (choc thermique)."
                ],
                "medical_orientation": "Prise en charge à l'Hôpital de Zone de Malanville pour réhydratation intraveineuse.",
                "medical_referral": "Prise en charge à l'Hôpital de Zone de Malanville pour réhydratation intraveineuse.",
                "simple_summary": "Coup de chaleur sérieux : mettez le patient à l'ombre, rafraîchissez son corps avec de l'eau et conduisez-le au centre de santé pour réhydratation."
            },
            "status": "en_cours",
            "assigned_service": {
                "facility_name": "Hôpital de Zone Malanville",
                "facility_type": "hopital_de_zone",
                "facility_phone": "+229 23 67 01 10",
                "department": "Alibori",
                "commune": "Malanville",
                "intervention_type": "consultation",
                "instructions": "Patient perfusé en salle d'observation. Surveillance tensionnelle.",
                "assigned_by": agent_npi,
                "assigned_at": now - timedelta(hours=6),
            },
            "resolution_notes": None,
            "is_demo": True,
            "created_at": now - timedelta(hours=8),
            "updated_at": now - timedelta(hours=6),
        },
        # 6. Borgou / Parakou : Paludisme grave enfant d'exploitant (Résolu)
        {
            "npi": farmer_users[3]["npi"] if len(farmer_users) > 3 else "0100000013",
            "patient_name": "Mariam Bio Tchané",
            "patient_relation": "membre_famille",
            "phone": "+229 97 88 99 00",
            "department": "Borgou",
            "commune": "Parakou",
            "locality": "Campement agricole de Baké",
            "land_id": None,
            "symptoms": "Forte fièvre à 39.8°C, convulsions fébriles brèves, refus de s'alimenter et frissons intenses.",
            "suspected_cause": "Paludisme grave à Plasmodium falciparum",
            "work_related": False,
            "urgency_perceived": "urgente",
            "urgency_level": "urgente",
            "urgency_label": "Urgence pédiatrique - Paludisme grave",
            "category": "infectieux_paludisme",
            "category_label": "Accès fébrile et infectieux (Paludisme)",
            "ai_recommendation": {
                "urgency_level": "urgente",
                "urgency_label": "Urgence pédiatrique - Paludisme grave",
                "category": "infectieux_paludisme",
                "category_label": "Accès fébrile et infectieux (Paludisme)",
                "first_aid_steps": [
                    "Déshabiller l'enfant et le garder dans une pièce aérée.",
                    "Appliquer des linges tièdes (non froids) sur le front et l'abdomen.",
                    "Transporter sans attendre vers le service pédiatrique du CHUD."
                ],
                "things_to_avoid": [
                    "NE PAS baigner dans de l'eau glacée (danger de convulsions réactionnelles).",
                    "NE PAS tenter d'automédication sans test TDR."
                ],
                "avoid": [
                    "NE PAS baigner dans de l'eau glacée (danger de convulsions réactionnelles).",
                    "NE PAS tenter d'automédication sans test TDR."
                ],
                "medical_orientation": "Prise en charge pédiatrique au CHUD Borgou (Parakou).",
                "medical_referral": "Prise en charge pédiatrique au CHUD Borgou (Parakou).",
                "simple_summary": "Paludisme grave suspecté : découvrez l'enfant, appliquez des linges tièdes et conduisez-le d'urgence au CHUD de Parakou pour injection d'antipaludiques."
            },
            "status": "resolu",
            "assigned_service": {
                "facility_name": "CHUD Borgou (Parakou)",
                "facility_type": "hopital_de_zone",
                "facility_phone": "+229 23 61 03 80",
                "department": "Borgou",
                "commune": "Parakou",
                "intervention_type": "consultation",
                "instructions": "Admission en pédiatrie pour protocole Artésunate.",
                "assigned_by": agent_npi,
                "assigned_at": now - timedelta(days=3),
            },
            "resolution_notes": "Traitement par Artésunate injectable puis relais ACT. Fièvre résolue, enfant guéri et rentré au domicile.",
            "is_demo": True,
            "created_at": now - timedelta(days=4),
            "updated_at": now - timedelta(days=1),
        },
        # 7. Zou / Bohicon : Irritation oculaire herbicide (En cours)
        {
            "npi": farmer_users[4]["npi"] if len(farmer_users) > 4 else "0100000014",
            "patient_name": "Koffi Dossou",
            "patient_relation": "ouvrier_agricole",
            "phone": "+229 96 55 66 77",
            "department": "Zou",
            "commune": "Bohicon",
            "locality": "Champ de maïs de Zakpota",
            "land_id": None,
            "symptoms": "Irritation oculaire vive, toux quinteuse persistante et céphalées après mélange d'herbicides sans lunettes de protection.",
            "suspected_cause": "Projections et vapeurs de désherbant",
            "work_related": True,
            "urgency_perceived": "moderee",
            "urgency_level": "moderee",
            "urgency_label": "Urgence modérée - Projection chimique",
            "category": "intoxication_pesticide",
            "category_label": "Intoxication par produit phytosanitaire",
            "ai_recommendation": {
                "urgency_level": "moderee",
                "urgency_label": "Urgence modérée - Projection chimique",
                "category": "intoxication_pesticide",
                "category_label": "Intoxication par produit phytosanitaire",
                "first_aid_steps": [
                    "Rincer abondamment les yeux ouverts à l'eau claire tempérée pendant 15 minutes.",
                    "S'asseoir au grand air et respirer calmement.",
                    "Changer de vêtements et laver les mains et avant-bras."
                ],
                "things_to_avoid": [
                    "NE PAS se frotter les yeux avec les mains sales.",
                    "NE PAS utiliser de collyre médicamenteux sans prescription."
                ],
                "avoid": [
                    "NE PAS se frotter les yeux avec les mains sales.",
                    "NE PAS utiliser de collyre médicamenteux sans prescription."
                ],
                "medical_orientation": "Consultation au CSA Bohicon pour examen ophtalmique et traitement apaisant.",
                "medical_referral": "Consultation au CSA Bohicon pour examen ophtalmique et traitement apaisant.",
                "simple_summary": "Projection chimique oculaire : rincez abondamment à l'eau claire sans frotter et consultez le centre de santé pour contrôle cornéen."
            },
            "status": "en_cours",
            "assigned_service": {
                "facility_name": "Centre de Santé d'Arrondissement (CSA) Bohicon",
                "facility_type": "centre_de_sante",
                "facility_phone": "+229 22 51 03 45",
                "department": "Zou",
                "commune": "Bohicon",
                "intervention_type": "consultation",
                "instructions": "Rinçage oculaire au sérum physiologique et repos.",
                "assigned_by": agent_npi,
                "assigned_at": now - timedelta(hours=12),
            },
            "resolution_notes": None,
            "is_demo": True,
            "created_at": now - timedelta(hours=14),
            "updated_at": now - timedelta(hours=12),
        },
        # 8. Plateau / Pobè : Chute d'arbre (Signalé en attente)
        {
            "npi": farmer_users[5]["npi"] if len(farmer_users) > 5 else "0100000015",
            "patient_name": "Kpèdétin Ahouandjinou",
            "patient_relation": "exploitant",
            "phone": "+229 97 12 34 56",
            "department": "Plateau",
            "commune": "Pobè",
            "locality": "Palmeraie d'Adja-Ouèrè",
            "land_id": None,
            "symptoms": "Chute d'une hauteur de 3 mètres lors de la coupe des régimes de palme. Douleur intense au bas du dos et impotence fonctionnelle.",
            "suspected_cause": "Rupture de sangle de grimpe",
            "work_related": True,
            "urgency_perceived": "urgente",
            "urgency_level": "urgente",
            "urgency_label": "Urgence traumatique - Suspicion fracture",
            "category": "traumatisme_agricole",
            "category_label": "Traumatisme et blessure agricole",
            "ai_recommendation": {
                "urgency_level": "urgente",
                "urgency_label": "Urgence traumatique - Suspicion fracture",
                "category": "traumatisme_agricole",
                "category_label": "Traumatisme et blessure agricole",
                "first_aid_steps": [
                    "Ne pas déplacer le blessé et maintenir sa tête et son dos parfaitement alignés.",
                    "Couvrir d'un vêtement pour éviter le refroidissement en attendant les secours.",
                    "Parler calmement au patient pour le rassurer."
                ],
                "things_to_avoid": [
                    "NE JAMAIS tenter d'asseoir ou de faire marcher le blessé.",
                    "NE PAS plier le dos ni tourner la tête brutalement."
                ],
                "avoid": [
                    "NE JAMAIS tenter d'asseoir ou de faire marcher le blessé.",
                    "NE PAS plier le dos ni tourner la tête brutalement."
                ],
                "medical_orientation": "Évacuation médicalisée par brancard rigide vers l'Hôpital de Zone de Pobè/Kétou.",
                "medical_referral": "Évacuation médicalisée par brancard rigide vers l'Hôpital de Zone de Pobè/Kétou.",
                "simple_summary": "Chute de hauteur avec traumatisme du dos : ne mobilisez sous aucun prétexte la victime et attendez les secours équipés d'un brancard rigide."
            },
            "status": "signale",
            "assigned_service": None,
            "resolution_notes": None,
            "is_demo": True,
            "created_at": now - timedelta(hours=3),
            "updated_at": now - timedelta(hours=3),
        }
    ]

    await db["farmer_health_alerts"].insert_many(health_alerts)
    return len(health_alerts)


async def _seed_financial_services(db, rng, users, lands, now, agent_npi) -> tuple[int, int]:
    """Données de démonstration pour le catalogue d'offres financières et les dossiers de candidature."""
    demo_farmer = users[0]
    demo_land = next(l for l in lands if l["npi_owner"] == demo_farmer["npi"])

    offers = [
        {
            "title": "Microcrédit Campagne Intrants & Semences FNDA",
            "type": "credit",
            "category_label": "Campagne Agricole 2026",
            "institution": "CLCAM / FNDA",
            "description": "Facilité de trésorerie à taux bonifié pour l'acquisition de semences certifiées, engrais NPK/Urée et produits de traitement homologués.",
            "amount_min": 150000,
            "amount_max": 2000000,
            "currency": "FCFA",
            "interest_rate_pct": 3.5,
            "duration_months": 12,
            "grace_period_months": 3,
            "premium_rate_pct": None,
            "coverage_details": None,
            "subsidy_pct": None,
            "eligible_departments": [],
            "eligible_crops": ["Maïs", "Coton", "Soja", "Riz", "Maraîchage"],
            "min_performance_score": 40.0,
            "requirements": ["Parcelle déclarée au cadastre", "Absence de litige foncier", "Engagement de commercialisation"],
            "active": True,
            "is_demo": True,
            "created_at": now - timedelta(days=60),
            "updated_at": now - timedelta(days=60),
        },
        {
            "title": "Prêt Équipement & Mécanisation Agricole",
            "type": "credit",
            "category_label": "Investissement & Modernisation",
            "institution": "Banque Agricole / BOA",
            "description": "Financement à moyen terme pour l'acquisition de motoculteurs, motopompes solaires, batteuses et remorques agricoles.",
            "amount_min": 1000000,
            "amount_max": 15000000,
            "currency": "FCFA",
            "interest_rate_pct": 4.5,
            "duration_months": 36,
            "grace_period_months": 6,
            "premium_rate_pct": None,
            "coverage_details": None,
            "subsidy_pct": None,
            "eligible_departments": [],
            "eligible_crops": [],
            "min_performance_score": 50.0,
            "requirements": ["Au moins 2 saisons vérifiées", "Devis pro-forma du fournisseur agréé", "Apport personnel de 15%"],
            "active": True,
            "is_demo": True,
            "created_at": now - timedelta(days=50),
            "updated_at": now - timedelta(days=50),
        },
        {
            "title": "Assurance Sécheresse & Déficit Hydrique Indicielle",
            "type": "assurance",
            "category_label": "Protection Climat & Résilience",
            "institution": "AMAB Assurances",
            "description": "Couverture climatique paramétrique indexée sur les données satellites d'évapotranspiration et de pluviométrie. Indemnisation automatique en cas de rupture des pluies.",
            "amount_min": 200000,
            "amount_max": 5000000,
            "currency": "FCFA",
            "interest_rate_pct": None,
            "duration_months": None,
            "grace_period_months": None,
            "premium_rate_pct": 4.0,
            "coverage_details": "Franchise 10 %, déclenchement indiciel satellite météo certifié",
            "subsidy_pct": None,
            "eligible_departments": ["Ouémé", "Plateau", "Borgou", "Alibori", "Zou", "Collines"],
            "eligible_crops": ["Maïs", "Coton", "Soja", "Riz"],
            "min_performance_score": None,
            "requirements": ["Géoréférencement précis de la parcelle", "Déclaration de date de semis"],
            "active": True,
            "is_demo": True,
            "created_at": now - timedelta(days=45),
            "updated_at": now - timedelta(days=45),
        },
        {
            "title": "Assurance Multirisque Récolte Coton & Soja",
            "type": "assurance",
            "category_label": "Assurance Récolte Complète",
            "institution": "CNAR Bénin",
            "description": "Protection contre les ravageurs majeurs, inondations subites et grêle pour les filières stratégiques d'exportation.",
            "amount_min": 300000,
            "amount_max": 8000000,
            "currency": "FCFA",
            "interest_rate_pct": None,
            "duration_months": None,
            "grace_period_months": None,
            "premium_rate_pct": 4.8,
            "coverage_details": "Couverture jusqu'à 80% du rendement historique prouvé",
            "subsidy_pct": None,
            "eligible_departments": ["Borgou", "Alibori", "Atacora", "Donga"],
            "eligible_crops": ["Coton", "Soja"],
            "min_performance_score": 45.0,
            "requirements": ["Parcelle vérifiée sans litige", "Respect du calendrier d'épandage"],
            "active": True,
            "is_demo": True,
            "created_at": now - timedelta(days=40),
            "updated_at": now - timedelta(days=40),
        },
        {
            "title": "Subvention Aménagement de Bas-Fonds Rizicoles",
            "type": "financement",
            "category_label": "Souveraineté Alimentaire MAEP",
            "institution": "Ministère de l'Agriculture (MAEP)",
            "description": "Appui non remboursable pour les travaux de nivellement, diguettes anti-érosion et maîtrise de l'eau sur parcelles rizicoles.",
            "amount_min": 500000,
            "amount_max": 5000000,
            "currency": "FCFA",
            "interest_rate_pct": None,
            "duration_months": None,
            "grace_period_months": None,
            "premium_rate_pct": None,
            "coverage_details": None,
            "subsidy_pct": 75.0,
            "eligible_departments": ["Ouémé", "Couffo", "Mono", "Zou", "Atacora"],
            "eligible_crops": ["Riz"],
            "min_performance_score": 45.0,
            "requirements": ["Titre ou convention d'exploitation valide", "Engagement de double culture annuelle"],
            "active": True,
            "is_demo": True,
            "created_at": now - timedelta(days=30),
            "updated_at": now - timedelta(days=30),
        },
        {
            "title": "Prime d'Installation Jeune Exploitant Maraîcher",
            "type": "financement",
            "category_label": "Promotion de la Jeunesse Agricole",
            "institution": "Fonds National de Développement Agricole (FNDA)",
            "description": "Dotation forfaitaire d'aide au démarrage pour les jeunes diplômés ou exploitants de moins de 35 ans s'installant en maraîchage agro-écologique.",
            "amount_min": 1000000,
            "amount_max": 3500000,
            "currency": "FCFA",
            "interest_rate_pct": None,
            "duration_months": None,
            "grace_period_months": None,
            "premium_rate_pct": None,
            "coverage_details": None,
            "subsidy_pct": 80.0,
            "eligible_departments": [],
            "eligible_crops": ["Maraîchage", "Tomate", "Piment", "Carotte", "Pastèque"],
            "min_performance_score": None,
            "requirements": ["Âge entre 18 et 35 ans", "Projet validé par un centre de formation ou ATDA"],
            "active": True,
            "is_demo": True,
            "created_at": now - timedelta(days=25),
            "updated_at": now - timedelta(days=25),
        }
    ]

    res_offers = await db["financial_offers"].insert_many(offers)
    offer_ids = [str(oid) for oid in res_offers.inserted_ids]

    farmer_1 = demo_farmer
    farmer_2 = users[4] if len(users) > 4 else demo_farmer
    farmer_3 = users[5] if len(users) > 5 else demo_farmer
    farmer_4 = users[6] if len(users) > 6 else demo_farmer

    applications = [
        # 1. Démo Exploitant - Crédit intrants approuvé
        {
            "offer_id": offer_ids[0],
            "offer_title": offers[0]["title"],
            "offer_type": offers[0]["type"],
            "offer_institution": offers[0]["institution"],
            "farmer_npi": farmer_1["npi"],
            "farmer_name": farmer_1["full_name"],
            "farmer_phone": farmer_1["phone"],
            "department": demo_land["department"],
            "commune": demo_land["commune"],
            "land_id": str(demo_land["_id"]),
            "land_title": demo_land.get("title", f"Parcelle {demo_land.get('crop_type', 'Maïs')} ({demo_land.get('commune', 'Dangbo')})"),
            "crop_type": "Maïs",
            "surface_ha": demo_land["surface_hectares"],
            "amount_requested": 800000,
            "amount_approved": 800000,
            "project_description": "Acquisition de semences hybrides certifiées et de 12 sacs d'engrais NPK/Urée pour la campagne principale.",
            "declared_harvest_estimate_kg": 5000,
            "guarantees_or_notes": "Nantissement sur récolte stockée dans le grenier communautaire de Dangbo.",
            "status": "approuve",
            "ai_evaluation": {
                "score": 82.5,
                "verdict": "favorable",
                "verdict_label": "Avis Favorable - Dossier Solvable",
                "strengths": [
                    "Parcelle vérifiée par les services cadastraux avec délimitation certifiée.",
                    "Score de performance agricole élevé (72/100) attestant d'une bonne maîtrise technique.",
                    "Ratio d'endettement faible : le prêt ne représente que 32 % de la récolte attendue."
                ],
                "risks": [
                    "Risque de pluviométrie tardive en début de saison nécessitant un semis étalé."
                ],
                "recommended_conditions": [
                    "Fourniture des factures d'achat auprès du distributeur d'engrais agréé.",
                    "Libération des fonds en deux tranches (50% labour, 50% sarclage/engrais)."
                ],
                "recommended_amount": 800000,
                "summary": "Dossier très sain présentant une assise technique et foncière irréprochable. Remboursement sécurisé par les rendements passés.",
                "farmer_advice": "Veillez à épandre l'urée en deux fractions pour maximiser l'efficience azotée de votre maïs.",
                "type_specific_metrics": {"debt_to_revenue_ratio": 0.32, "solvency_coverage_ratio": 3.12}
            },
            "agent_decision": {
                "status": "approuve",
                "decided_by_npi": agent_npi,
                "decided_by_name": "Démo Agent État",
                "amount_approved": 800000,
                "interest_rate_approved": 3.5,
                "duration_approved_months": 12,
                "conditions": [
                    "Déblocage 50% au labour, 50% au sarclage",
                    "Contrôle de conformité des semences certifiées"
                ],
                "motivation_or_notes": "Dossier exemplaire. Exploitant rigoureux et parcelle cadastrée sans litige.",
                "decided_at": now - timedelta(days=5),
            },
            "disbursement": None,
            "is_demo": True,
            "created_at": now - timedelta(days=12),
            "updated_at": now - timedelta(days=5),
        },
        # 2. Démo Exploitant - Assurance indicielle active
        {
            "offer_id": offer_ids[2],
            "offer_title": offers[2]["title"],
            "offer_type": offers[2]["type"],
            "offer_institution": offers[2]["institution"],
            "farmer_npi": farmer_1["npi"],
            "farmer_name": farmer_1["full_name"],
            "farmer_phone": farmer_1["phone"],
            "department": demo_land["department"],
            "commune": demo_land["commune"],
            "land_id": str(demo_land["_id"]),
            "land_title": demo_land.get("title", f"Parcelle {demo_land.get('crop_type', 'Maïs')} ({demo_land.get('commune', 'Dangbo')})"),
            "crop_type": "Maïs",
            "surface_ha": demo_land["surface_hectares"],
            "amount_requested": 1200000,
            "amount_approved": 1200000,
            "project_description": "Souscription d'une couverture indicielle contre le déficit hydrique sur maïs blanc.",
            "declared_harvest_estimate_kg": 5000,
            "guarantees_or_notes": "Police couplée au compte d'épargne agricole.",
            "status": "debourse_actif",
            "ai_evaluation": {
                "score": 76.0,
                "verdict": "favorable",
                "verdict_label": "Souscription Recommandée",
                "strengths": [
                    "Géoréférencement satellite haute précision disponible.",
                    "Historique de 3 saisons de récoltes régulières."
                ],
                "risks": ["Zone sujette à des poches de sécheresse décennales en juin."],
                "recommended_conditions": ["Franchise de 10% appliquée selon barème AMAB."],
                "recommended_amount": 1200000,
                "summary": "Risque assurable avec excellent ratio de solvabilité.",
                "farmer_advice": "Conservez le numéro de contrat pour la déclaration de semis par SMS.",
                "type_specific_metrics": {"climate_vulnerability": "moderee", "recommended_deductible_pct": 10}
            },
            "agent_decision": {
                "status": "approuve",
                "decided_by_npi": agent_npi,
                "decided_by_name": "Démo Agent État",
                "amount_approved": 1200000,
                "interest_rate_approved": None,
                "duration_approved_months": 12,
                "conditions": ["Validation de la délimitation parcellaire"],
                "motivation_or_notes": "Couverture validée avec prime subventionnée à 50% par le FNDA.",
                "decided_at": now - timedelta(days=20),
            },
            "disbursement": {
                "disbursed_at": now - timedelta(days=18),
                "contract_ref": "AGRI-ASSUR-8801",
                "payment_reference": "PRM-AMAB-2026-003",
                "disbursed_by": agent_npi,
                "notes": "Police d'assurance active pour la campagne 2026."
            },
            "is_demo": True,
            "created_at": now - timedelta(days=25),
            "updated_at": now - timedelta(days=18),
        },
        # 3. Démo Exploitant - Subvention bas-fond en cours
        {
            "offer_id": offer_ids[4],
            "offer_title": offers[4]["title"],
            "offer_type": offers[4]["type"],
            "offer_institution": offers[4]["institution"],
            "farmer_npi": farmer_1["npi"],
            "farmer_name": farmer_1["full_name"],
            "farmer_phone": farmer_1["phone"],
            "department": demo_land["department"],
            "commune": demo_land["commune"],
            "land_id": str(demo_land["_id"]),
            "land_title": demo_land.get("title", f"Parcelle {demo_land.get('crop_type', 'Maïs')} ({demo_land.get('commune', 'Dangbo')})"),
            "crop_type": "Riz",
            "surface_ha": 2.0,
            "amount_requested": 2500000,
            "amount_approved": None,
            "project_description": "Aménagement hydro-agricole de 2 hectares de bas-fond pour production de riz NERICA avec diguettes en terre battue.",
            "declared_harvest_estimate_kg": 7000,
            "guarantees_or_notes": "Participation communautaire en main-d'œuvre locale pour le terrassement.",
            "status": "soumis",
            "ai_evaluation": {
                "score": 84.0,
                "verdict": "favorable",
                "verdict_label": "Attribution Recommandée (Haute Priorité)",
                "strengths": [
                    "Alignement stratégique parfait avec le Programme National de Développement de la Filière Riz (PNDF-Riz).",
                    "Effet levier estimé à 2.8 × la subvention en volume de production annuelle.",
                    "Topographie propice à la rétention d'eau en bas-fond sans motopompe lourde."
                ],
                "risks": [
                    "Risque de crue soudaine nécessitant un déversoir de crue sécurisé."
                ],
                "recommended_conditions": [
                    "Visite technique de l'ingénieur du génie rural de l'ATDA avant terrassement.",
                    "Achat exclusif de semences homologuées certifiées MAEP."
                ],
                "recommended_amount": 2500000,
                "summary": "Projet structurant à forte valeur ajoutée locale contribuant directement à la sécurité alimentaire du département de l'Ouémé.",
                "farmer_advice": "Prévoyez les tranchées de drainage avant les grandes pluies pour faciliter le repiquage du riz.",
                "type_specific_metrics": {"strategic_crop_priority": "Filière prioritaire PAG", "leverage_multiplier": 2.8}
            },
            "agent_decision": None,
            "disbursement": None,
            "is_demo": True,
            "created_at": now - timedelta(days=2),
            "updated_at": now - timedelta(days=2),
        },
        # 4. Exploitant 2 - Crédit équipement approuvé (Banikoara)
        {
            "offer_id": offer_ids[1],
            "offer_title": offers[1]["title"],
            "offer_type": offers[1]["type"],
            "offer_institution": offers[1]["institution"],
            "farmer_npi": farmer_2["npi"],
            "farmer_name": farmer_2["full_name"],
            "farmer_phone": farmer_2["phone"],
            "department": "Alibori",
            "commune": "Banikoara",
            "land_id": None,
            "land_title": None,
            "crop_type": "Coton",
            "surface_ha": 6.5,
            "amount_requested": 4500000,
            "amount_approved": 4000000,
            "project_description": "Acquisition d'un motoculteur diesel 15 CV avec charrue et remorque pour préparation des sols cotonniers.",
            "declared_harvest_estimate_kg": 8500,
            "guarantees_or_notes": "Gage sur le matériel roulant avec assurance multirisque engin.",
            "status": "approuve",
            "ai_evaluation": {
                "score": 79.0,
                "verdict": "favorable",
                "verdict_label": "Avis Favorable - Dossier Solvable",
                "strengths": [
                    "Grande superficie cotonière (6.5 ha) justifiant pleinement la mécanisation.",
                    "Revenus cotonniers récurrents facilitant l'amortissement sur 36 mois."
                ],
                "risks": ["Coût de maintenance et disponibilité des pièces de rechange à Banikoara."],
                "recommended_conditions": ["Contrat d'entretien auprès d'un mécanicien agréé."],
                "recommended_amount": 4000000,
                "summary": "Projet de mécanisation viable et rentable. Montant ajusté à 4 000 000 FCFA avec apport de 500 000 FCFA.",
                "farmer_advice": "Partagez l'utilisation de l'engin avec vos voisins de coopérative pour accélérer l'amortissement.",
                "type_specific_metrics": {"debt_to_revenue_ratio": 0.47, "solvency_coverage_ratio": 2.1}
            },
            "agent_decision": {
                "status": "approuve",
                "decided_by_npi": agent_npi,
                "decided_by_name": "Démo Agent État",
                "amount_approved": 4000000,
                "interest_rate_approved": 4.0,
                "duration_approved_months": 36,
                "conditions": ["Gage du matériel avec carte grise au nom du FNDA", "Formation à l'entretien préventif"],
                "motivation_or_notes": "Accord favorable avec réfaction à 4M FCFA selon devis négocié avec le concessionnaire.",
                "decided_at": now - timedelta(days=7),
            },
            "disbursement": None,
            "is_demo": True,
            "created_at": now - timedelta(days=15),
            "updated_at": now - timedelta(days=7),
        },
        # 5. Exploitant 3 - Assurance multirisque active (Allada)
        {
            "offer_id": offer_ids[3],
            "offer_title": offers[3]["title"],
            "offer_type": offers[3]["type"],
            "offer_institution": offers[3]["institution"],
            "farmer_npi": farmer_3["npi"],
            "farmer_name": farmer_3["full_name"],
            "farmer_phone": farmer_3["phone"],
            "department": "Atlantique",
            "commune": "Allada",
            "land_id": None,
            "land_title": None,
            "crop_type": "Soja",
            "surface_ha": 3.0,
            "amount_requested": 800000,
            "amount_approved": 800000,
            "project_description": "Couverture d'assurance multirisque récolte pour 3 ha de soja biologique.",
            "declared_harvest_estimate_kg": 4500,
            "guarantees_or_notes": "Contrat d'agrégation avec une usine de transformation de soja locale.",
            "status": "debourse_actif",
            "ai_evaluation": {
                "score": 75.0,
                "verdict": "favorable",
                "verdict_label": "Souscription Recommandée",
                "strengths": ["Débouché commercial garanti avec acheteur agréé."],
                "risks": ["Sensibilité aux chenilles en phase de floraison."],
                "recommended_conditions": ["Signalement sous 48h en cas de sinistre constaté."],
                "recommended_amount": 800000,
                "summary": "Dossier conforme et risque bien maîtrisé.",
                "farmer_advice": "Vérifiez vos parcelles deux fois par semaine pour prévenir les attaques de noctuelles.",
                "type_specific_metrics": {"climate_vulnerability": "faible"}
            },
            "agent_decision": {
                "status": "approuve",
                "decided_by_npi": agent_npi,
                "decided_by_name": "Démo Agent État",
                "amount_approved": 800000,
                "interest_rate_approved": None,
                "duration_approved_months": 12,
                "conditions": ["Contrat d'agrégation vérifié"],
                "motivation_or_notes": "Souscription validée pour la campagne soja.",
                "decided_at": now - timedelta(days=10),
            },
            "disbursement": {
                "disbursed_at": now - timedelta(days=9),
                "contract_ref": "AGRI-ASSUR-9204",
                "payment_reference": "PRM-CNAR-2026-118",
                "disbursed_by": agent_npi,
                "notes": "Police activée."
            },
            "is_demo": True,
            "created_at": now - timedelta(days=14),
            "updated_at": now - timedelta(days=9),
        },
        # 6. Exploitant 4 - Crédit rejeté pour surendettement (Parakou)
        {
            "offer_id": offer_ids[0],
            "offer_title": offers[0]["title"],
            "offer_type": offers[0]["type"],
            "offer_institution": offers[0]["institution"],
            "farmer_npi": farmer_4["npi"],
            "farmer_name": farmer_4["full_name"],
            "farmer_phone": farmer_4["phone"],
            "department": "Borgou",
            "commune": "Parakou",
            "land_id": None,
            "land_title": None,
            "crop_type": "Maïs",
            "surface_ha": 0.8,
            "amount_requested": 1800000,
            "amount_approved": None,
            "project_description": "Demande de fonds de roulement pour intrants et main-d'œuvre.",
            "declared_harvest_estimate_kg": 1500,
            "guarantees_or_notes": "Pas de garantie matérielle disponible.",
            "status": "rejete",
            "ai_evaluation": {
                "score": 32.0,
                "verdict": "defavorable",
                "verdict_label": "Avis Défavorable - Risque Élevé",
                "strengths": ["Motivation de l'exploitant pour intensifier la culture."],
                "risks": [
                    "Surendettement manifeste : le montant demandé (1.8M FCFA) est 6 fois supérieur à la valeur de la récolte (300 000 FCFA).",
                    "Surface très modeste (0.8 ha) ne permettant pas de couvrir les échéances de prêt."
                ],
                "recommended_conditions": ["Restructurer la demande à un montant maximal de 250 000 FCFA."],
                "recommended_amount": 250000,
                "summary": "Incompatibilité majeure entre le montant sollicité et la capacité réelle de production de la parcelle.",
                "farmer_advice": "Ajustez votre demande à la taille réelle de votre exploitation (0.8 ha) pour éviter le surendettement.",
                "type_specific_metrics": {"debt_to_revenue_ratio": 6.0, "solvency_coverage_ratio": 0.16}
            },
            "agent_decision": {
                "status": "rejete",
                "decided_by_npi": agent_npi,
                "decided_by_name": "Démo Agent État",
                "amount_approved": None,
                "interest_rate_approved": None,
                "duration_approved_months": None,
                "conditions": [],
                "motivation_or_notes": "Capacité financière insuffisante. Le montant demandé excède très largement la valeur attendue de la récolte.",
                "decided_at": now - timedelta(days=3),
            },
            "disbursement": None,
            "is_demo": True,
            "created_at": now - timedelta(days=8),
            "updated_at": now - timedelta(days=3),
        }
    ]

    await db["financial_applications"].insert_many(applications)
    return len(offers), len(applications)


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
                "verification_status": "verifiee" if npi == DEMO_ACCOUNTS[0][0] else rng.choices(["declaree", "verifiee", "rejetee"], [40, 57, 3])[0],
                "boundary_history": [], "ownership_history": [], "is_demo": True, "created_at": created, "updated_at": created,
            })
    res = await db["lands"].insert_many(lands)
    for land, oid in zip(lands, res.inserted_ids):
        land["_id"] = oid
    counts["lands"] = len(lands)

    # --- Litiges : quelques chevauchements volontaires
    disputes = []
    for land in rng.sample([l for l in lands if l["npi_owner"] != DEMO_ACCOUNTS[0][0]], 6):
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
    skill = {npi: rng.uniform(0.6, 1.25) for npi in farmer_npis}  # certains exploitants sont plus performants
    skill[DEMO_ACCOUNTS[0][0]] = 1.2
    for land in lands:
        demo = land["npi_owner"] == DEMO_ACCOUNTS[0][0]
        if not demo and rng.random() < 0.3:
            continue
        for season in SEASONS:
            if demo or rng.random() < 0.8:
                actual = round(land["estimated_yield_kg"] * skill[land["npi_owner"]] * rng.uniform(0.85, 1.1))
                harvests.append({"land_id": str(land["_id"]), "npi_owner": land["npi_owner"], "season": season,
                                 "crop_type": land["crop_type"], "actual_yield_kg": actual,
                                 "harvest_date": f"{season[:4]}-{'07' if season.endswith('A') else '12'}-15",
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

    # --- Domaine privé de l'État : une terre à chaque étape de la procédure
    counts.update(await _seed_state_domains(db, rng, polys, farmer_npis, now))

    # --- Stocks du compte exploitant (conseiller de stockage)
    demo_land = next(l for l in lands if l["npi_owner"] == DEMO_ACCOUNTS[0][0])
    lots = [
        {"product": "Maïs", "quantity_kg": 1200, "initial_quantity_kg": 1200, "harvest_date": (now - timedelta(days=45)).date().isoformat(),
         "storage_method": "grenier_traditionnel", "moisture_pct": 16, "last_moisture_pct": 16},
        {"product": "Soja", "quantity_kg": 600, "initial_quantity_kg": 600, "harvest_date": (now - timedelta(days=20)).date().isoformat(),
         "storage_method": "sac_hermetique", "moisture_pct": 11, "last_moisture_pct": 11},
    ]
    await db["stock_lots"].insert_many([{**l, "npi": DEMO_ACCOUNTS[0][0], "land_id": str(demo_land["_id"]), "department": demo_land["department"],
                                         "commune": demo_land["commune"], "status": "en_stock", "checks": [], "is_demo": True,
                                         "created_at": now, "updated_at": now} for l in lots])
    counts["stock_lots"] = len(lots)

    # --- Données de santé des exploitants (assistance IA et coordination territoriale)
    counts["farmer_health_alerts"] = await _seed_farmer_health(db, rng, users, lands, now, agent_npi)

    # --- Données de crédit, assurance et financement agricole (FNDA / MAEP)
    counts["financial_offers"], counts["financial_applications"] = await _seed_financial_services(db, rng, users, lands, now, agent_npi)

    # --- Quelques notifications pour les comptes de démonstration
    notes = [
        {"npi": DEMO_ACCOUNTS[0][0], "type": "sanitary_alert", "title": "Alerte : Chenille légionnaire d'automne",
         "message": "9 cas signalés à Dangbo ces 30 derniers jours. Surveillez vos champs.", "pictogram": "bug"},
        {"npi": DEMO_ACCOUNTS[0][0], "type": "offer_interest", "title": "Un acheteur est intéressé",
         "message": "Démo Acheteur est intéressé(e) par votre offre.", "pictogram": "buyer"},
        {"npi": DEMO_ACCOUNTS[0][0], "type": "health_assigned", "title": "Service de santé assigné",
         "message": "Votre alerte santé a été confiée à : Hôpital de Zone Dangbo-Adjohoun-Bonou. Équipe SAMU mobilisée.", "pictogram": "hospital"},
        {"npi": DEMO_ACCOUNTS[0][0], "type": "finance_decision", "title": "Crédit approuvé : 800 000 FCFA",
         "message": "Votre demande de microcrédit intrants FNDA a été validée par la CLCAM.", "pictogram": "buyer"},
        {"npi": agent_npi, "type": "sanitary_alert", "title": "Alerte : Chenille de la capsule",
         "message": "7 cas signalés à Banikoara ces 30 derniers jours.", "pictogram": "bug"},
        {"npi": agent_npi, "type": "health_alert", "title": "Alerte vitale : Intoxication pesticide",
         "message": "Urgence vitale signalée à Banikoara : ouvrier agricole intoxiqué lors d'une pulvérisation.", "pictogram": "heart"},
        {"npi": agent_npi, "type": "finance_application", "title": "Nouveau dossier de financement à instruire",
         "message": "Demande de subvention aménagement de bas-fond déposée à Dangbo (2 500 000 FCFA).", "pictogram": "bank"},
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
