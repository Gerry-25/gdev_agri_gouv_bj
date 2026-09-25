"""Zones agroécologiques (ZAE) du Bénin.

Il n'existe pas de service en ligne : la zone est **suggérée** à partir de la commune ou du
département, puis **confirmée par l'agent** dans le relevé de terrain.
Seule la liste des communes de la zone 6 est intégrée ici ; les autres suggestions sont des zones
candidates par département, à compléter avec la carte officielle (SNISA / MAEP).
"""
import unicodedata

ZONES = {
    1: "Zone de l'extrême nord",
    2: "Zone cotonnière du nord",
    3: "Zone vivrière du sud-Borgou",
    4: "Zone ouest-Atacora",
    5: "Zone cotonnière du centre",
    6: "Zone de terre de barre",
    7: "Zone de la dépression",
    8: "Zone des pêcheries",
}

# Caractéristiques documentées (les autres zones sont à compléter avec les services du MAEP)
DESCRIPTIONS = {
    1: "Une saison des pluies ; pluviométrie moyenne inférieure à 900 mm ; période culturale d'environ 120 jours ; "
       "sols ferrugineux et sols alluviaux fertiles du fleuve Niger.",
    5: "Transition : deux saisons des pluies au sud, une au nord ; 1000 à 1200 mm par an ; sols ferrugineux sur socle cristallin, très variables.",
    6: "Deux saisons des pluies (mars-juillet, octobre-novembre) ; 1000 à 1400 mm par an ; sols ferrallitiques dits « de barre ».",
}

ZONE_6_COMMUNES = {
    "abomey-calavi", "allada", "kpomasse", "tori-bossito", "ze", "djakotomey", "dogbo", "klouekanme", "houeyogbe",
    "toviklin", "adjarra", "akpro-missérété", "akpro-misserete", "avrankou", "ifangni", "porto-novo", "sakete",
    "abomey", "agbangnizoun", "agbagnizoun", "bohicon", "cove", "za-kpota", "zagnanado",
}

DEPARTMENT_CANDIDATES = {
    "Alibori": [1, 2], "Atacora": [4, 2], "Borgou": [2, 3], "Donga": [4, 3], "Collines": [5], "Zou": [5, 6, 7],
    "Couffo": [6, 7], "Mono": [6, 8], "Atlantique": [6, 7, 8], "Littoral": [8], "Ouémé": [6, 8], "Plateau": [6, 7],
}


def _key(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().strip().lower()


def suggest(department: str, commune: str, confirmed: int | None = None) -> dict:
    if confirmed:
        candidates, basis = [confirmed], "confirmée par l'agent"
    elif _key(commune) in ZONE_6_COMMUNES:
        candidates, basis = [6], "commune de la zone de terre de barre"
    else:
        candidates, basis = DEPARTMENT_CANDIDATES.get(department, []), "zones candidates du département, à confirmer"
    return {
        "confirmed": bool(confirmed),
        "basis": basis,
        "candidates": [{"zone": z, "name": ZONES[z], "description": DESCRIPTIONS.get(z)} for z in candidates],
    }
