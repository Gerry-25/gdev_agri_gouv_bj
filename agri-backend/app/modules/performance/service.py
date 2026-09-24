"""Score de performance des exploitants (0 à 100), explicable critère par critère.

Principes :
- seules les récoltes sur des parcelles **vérifiées par un agent** (et les récoltes déclarées sur une
  concession de l'État) sont prises en compte ;
- la productivité est **comparée aux pairs** : rendement à l'hectare rapporté à la médiane de la même
  culture dans le même département (médiane nationale de la culture si trop peu de données locales) ;
- l'éligibilité aux appels à candidatures exige un minimum de saisons et l'absence de litige ouvert.

Le calcul est fait à la demande. Au-delà de quelques dizaines de milliers de récoltes, il faudra le
précalculer (tâche planifiée) et stocker le résultat.
"""
from collections import defaultdict
from datetime import timedelta
from statistics import mean, median, pstdev

from app.core.config import settings
from app.core.utils import utcnow

WEIGHTS = {"productivity": 0.40, "accuracy": 0.15, "regularity": 0.15, "compliance": 0.15, "market": 0.15}
LABELS = {
    "productivity": "Productivité comparée aux exploitants voisins (même culture)",
    "accuracy": "Fiabilité des prévisions de récolte",
    "regularity": "Régularité d'une saison à l'autre",
    "compliance": "Parcelles vérifiées et absence de litige",
    "market": "Ventes déclarées sur les 12 derniers mois",
}
_MIN_LOCAL_SAMPLES = 3


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


async def _harvest_records(db) -> list[dict]:
    """Récoltes comptabilisables : parcelles vérifiées + rapports de concession."""
    verified = {str(l["_id"]): l async for l in db["lands"].find(
        {"verification_status": "verifiee"}, {"surface_hectares": 1, "department": 1})}
    records = []
    async for h in db["harvests"].find({"land_id": {"$in": list(verified)}}):
        land = verified[h["land_id"]]
        if land["surface_hectares"] > 0:
            records.append({"npi": h["npi_owner"], "crop": h["crop_type"], "department": land["department"], "season": h["season"],
                            "surface": land["surface_hectares"], "actual": h["actual_yield_kg"], "estimated": h.get("estimated_yield_kg")})
    async for r in db["concession_reports"].find({}):
        if r["area_cultivated_ha"] > 0:
            records.append({"npi": r["farmer_npi"], "crop": r["crop_type"], "department": r["department"], "season": r["season"],
                            "surface": r["area_cultivated_ha"], "actual": r["actual_yield_kg"], "estimated": r.get("expected_yield_kg")})
    for rec in records:
        rec["yield_ha"] = rec["actual"] / rec["surface"]
    return records


def _medians(records: list[dict]) -> tuple[dict, dict]:
    local, national = defaultdict(list), defaultdict(list)
    for r in records:
        local[(r["crop"], r["department"])].append(r["yield_ha"])
        national[r["crop"]].append(r["yield_ha"])
    return ({k: median(v) for k, v in local.items() if len(v) >= _MIN_LOCAL_SAMPLES},
            {k: median(v) for k, v in national.items()})


def _score_farmer(npi: str, recs: list[dict], lands: list[dict], sold_12m: int, medians) -> dict:
    local_med, national_med = medians
    reasons = []

    # Productivité : ratio au rendement médian des pairs, pondéré par la surface (médiane = 50/100)
    ratios, by_season = [], defaultdict(list)
    for r in recs:
        ref = local_med.get((r["crop"], r["department"])) or national_med.get(r["crop"])
        if ref:
            ratio = r["yield_ha"] / ref
            ratios.append((ratio, r["surface"]))
            by_season[r["season"]].append(ratio)
    productivity = _clamp(50 * sum(x * w for x, w in ratios) / sum(w for _, w in ratios)) if ratios else 0.0
    avg_ratio = round(sum(x * w for x, w in ratios) / sum(w for _, w in ratios), 2) if ratios else None

    errors = [abs(r["actual"] - r["estimated"]) / r["estimated"] for r in recs if r.get("estimated")]
    accuracy = _clamp(100 * (1 - mean(errors))) if errors else 0.0

    seasons = len(by_season)
    if seasons >= 2:
        season_means = [mean(v) for v in by_season.values()]
        cv = pstdev(season_means) / mean(season_means) if mean(season_means) else 1
        regularity = _clamp(100 * (1 - cv))
    else:
        regularity = 50.0  # neutre faute de recul

    n = len(lands)
    verified = sum(1 for l in lands if l.get("verification_status") == "verifiee")
    rejected = sum(1 for l in lands if l.get("verification_status") == "rejetee")
    in_dispute = sum(1 for l in lands if l.get("dispute_flag"))
    compliance = _clamp(100 * verified / n - 30 * rejected - 50 * (in_dispute > 0)) if n else 0.0

    market = _clamp(25 * sold_12m)

    comps = {"productivity": productivity, "accuracy": accuracy, "regularity": regularity, "compliance": compliance, "market": market}
    details = {
        "productivity": f"Rendement moyen = {avg_ratio} × la médiane des pairs" if avg_ratio is not None else "Aucune récolte vérifiée",
        "accuracy": f"Écart moyen prévision/réel : {round(100 * mean(errors))} %" if errors else "Aucune prévision comparable",
        "regularity": f"{seasons} saison(s) comparée(s)" if seasons >= 2 else "Moins de 2 saisons : valeur neutre",
        "compliance": f"{verified}/{n} parcelle(s) vérifiée(s), {in_dispute} en litige, {rejected} rejetée(s)",
        "market": f"{sold_12m} vente(s) déclarée(s)",
    }
    score = round(sum(WEIGHTS[k] * v for k, v in comps.items()), 1)

    if seasons < settings.PERFORMANCE_MIN_SEASONS:
        reasons.append(f"Au moins {settings.PERFORMANCE_MIN_SEASONS} saisons de récolte sur parcelles vérifiées sont nécessaires ({seasons} actuellement).")
    if in_dispute:
        reasons.append("Une parcelle est en litige : l'éligibilité est suspendue jusqu'à sa clôture.")

    return {
        "npi": npi,
        "score": score,
        "eligible": not reasons,
        "ineligibility_reasons": reasons,
        "components": [
            {"key": k, "label": LABELS[k], "score": round(comps[k], 1), "weight": WEIGHTS[k], "detail": details[k]} for k in WEIGHTS
        ],
        "stats": {
            "seasons": seasons,
            "harvests_counted": len(recs),
            "verified_surface_ha": round(sum(l["surface_hectares"] for l in lands if l.get("verification_status") == "verifiee"), 2),
            "parcels": n,
            "crops": sorted({r["crop"] for r in recs}),
            "departments": sorted({l["department"] for l in lands}),
        },
    }


async def compute_scores(db, npis: list[str] | None = None) -> dict[str, dict]:
    """Scores des exploitants demandés (tous par défaut). Les médianes utilisent toujours toutes les données."""
    records = await _harvest_records(db)
    medians = _medians(records)
    user_filter = {"role": "farmer"} if npis is None else {"npi": {"$in": npis}}
    users = {u["npi"]: u async for u in db["users"].find(user_filter, {"npi": 1, "full_name": 1})}
    targets = list(users) if npis is None else npis

    recs_by, lands_by = defaultdict(list), defaultdict(list)
    for r in records:
        recs_by[r["npi"]].append(r)
    async for l in db["lands"].find({"npi_owner": {"$in": targets}},
                                    {"npi_owner": 1, "verification_status": 1, "dispute_flag": 1, "surface_hectares": 1, "department": 1}):
        lands_by[l["npi_owner"]].append(l)
    since = utcnow() - timedelta(days=365)
    sold = defaultdict(int)
    async for o in db["market_offers"].find({"farmer_npi": {"$in": targets}, "status": "sold", "sold_at": {"$gte": since}}, {"farmer_npi": 1}):
        sold[o["farmer_npi"]] += 1

    out = {}
    for npi in targets:
        result = _score_farmer(npi, recs_by[npi], lands_by[npi], sold[npi], medians)
        result["full_name"] = users.get(npi, {}).get("full_name")
        out[npi] = result
    return out


async def compute_score(db, npi: str) -> dict:
    return (await compute_scores(db, [npi]))[npi]
