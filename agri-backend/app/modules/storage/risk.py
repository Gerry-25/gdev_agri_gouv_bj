"""Évaluation du risque de pertes en stock, par des règles simples et explicables.

Les valeurs ci-dessous sont des **repères indicatifs** tirés des bonnes pratiques de conservation ;
elles doivent être calibrées avec l'INRAB et les services de vulgarisation avant un usage à grande échelle.
"""
from datetime import date, timedelta

# Humidité maximale conseillée pour stocker (%), par produit
SAFE_MOISTURE = {"maïs": 13, "mais": 13, "sorgho": 13, "mil": 13, "riz": 14, "niébé": 12, "niebe": 12, "soja": 12,
                 "arachide": 9, "anacarde": 10, "cajou": 10}
# Produits frais : stockage court, risque élevé quelle que soit la méthode
PERISHABLE = {"tomate", "igname", "manioc", "ananas", "piment", "oignon"}

METHOD_RISK = {  # 0 = faible, 1 = moyen, 2 = élevé
    "sac_hermetique": 0, "fut_hermetique": 0, "magasin_ventile": 1, "sac_polypropylene": 1, "grenier_traditionnel": 2, "autre": 1,
}
METHOD_LABEL = {"sac_hermetique": "sacs hermétiques", "fut_hermetique": "fûts hermétiques", "magasin_ventile": "magasin ventilé",
                "sac_polypropylene": "sacs en polypropylène", "grenier_traditionnel": "grenier traditionnel", "autre": "autre méthode"}
HUMID_DEPARTMENTS = {"Littoral", "Atlantique", "Ouémé", "Mono", "Couffo", "Plateau", "Zou"}


def assess(lot: dict, today: date | None = None) -> dict:
    today = today or date.today()
    product = lot["product"].lower()
    factors, score = [], METHOD_RISK.get(lot["storage_method"], 1)
    factors.append(f"Stockage en {METHOD_LABEL.get(lot['storage_method'], 'autre méthode')}")

    stored_days = (today - date.fromisoformat(str(lot["harvest_date"])[:10])).days
    if product in PERISHABLE:
        score += 2
        factors.append("Produit frais : à écouler ou transformer rapidement")
    if stored_days > 120:
        score += 1
        factors.append(f"Stocké depuis {stored_days} jours")

    moisture = lot.get("last_moisture_pct", lot.get("moisture_pct"))
    target = SAFE_MOISTURE.get(product)
    if moisture is not None and target and moisture > target:
        score += 2
        factors.append(f"Humidité {moisture:.0f} % au-dessus du seuil conseillé ({target} %)")
    elif moisture is None and target:
        factors.append(f"Humidité non mesurée (seuil conseillé : {target} %)")

    if lot.get("department") in HUMID_DEPARTMENTS and lot["storage_method"] not in ("sac_hermetique", "fut_hermetique"):
        score += 1
        factors.append("Climat humide du sud : risque de moisissures")
    if lot.get("insects_seen"):
        score += 2
        factors.append("Insectes observés au dernier contrôle")
    if lot.get("mold_seen"):
        score += 2
        factors.append("Moisissures observées au dernier contrôle")

    level = "faible" if score <= 1 else "moyen" if score <= 3 else "eleve"
    interval = {"faible": 30, "moyen": 14, "eleve": 7}[level]
    last = date.fromisoformat(str(lot.get("last_check_date") or lot["harvest_date"])[:10])
    return {"level": level, "score": score, "factors": factors, "safe_moisture_pct": target,
            "check_every_days": interval, "next_check_date": (max(last, today - timedelta(days=interval)) + timedelta(days=interval)).isoformat(),
            "stored_days": stored_days}
