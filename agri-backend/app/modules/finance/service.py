import logging
from typing import Any, Optional

from app.core.utils import serialize_doc, utcnow
from app.core import ai_service
from app.modules.finance.schemas import (
    ApplicationCreate,
    FinancialAiEvaluation,
    OfferOut,
)
from app.modules.performance.service import compute_scores

logger = logging.getLogger(__name__)

# Prix moyens indicatifs et rendements de référence au Bénin (FCFA/kg et kg/ha)
CROP_BENCHMARKS = {
    "Maïs": {"yield_ha": 2200, "price_kg": 200, "label": "Céréale vivrière"},
    "Riz": {"yield_ha": 3500, "price_kg": 260, "label": "Céréale stratégique"},
    "Coton": {"yield_ha": 1300, "price_kg": 300, "label": "Culture de rente industrielle"},
    "Soja": {"yield_ha": 1500, "price_kg": 350, "label": "Légumineuse oléagineuse"},
    "Maraîchage": {"yield_ha": 8000, "price_kg": 250, "label": "Cultures maraîchères périurbaines"},
    "Piment": {"yield_ha": 4000, "price_kg": 400, "label": "Épice et maraîchage"},
    "Tomate": {"yield_ha": 7000, "price_kg": 200, "label": "Maraîchage intensif"},
    "Ananas": {"yield_ha": 12000, "price_kg": 180, "label": "Filière fruitière d'exportation"},
    "Manioc": {"yield_ha": 9000, "price_kg": 80, "label": "Tubercule de sécurité"},
    "Igname": {"yield_ha": 8000, "price_kg": 150, "label": "Tubercule vivrier"},
    "Palmier à huile": {"yield_ha": 5000, "price_kg": 120, "label": "Arboriculture pérenne"},
}
DEFAULT_CROP_BENCHMARK = {"yield_ha": 2000, "price_kg": 250, "label": "Culture polyvalente"}


async def get_farmer_profile_context(db, npi: str) -> dict[str, Any]:
    """Récupère l'historique complet de l'exploitant : performance, foncier, récoltes, litiges."""
    # 1. Performance agricole
    scores = await compute_scores(db, [npi])
    perf = scores.get(npi, {})

    # 2. Parcelles déclarées et vérifiées
    lands = [l async for l in db["lands"].find({"npi_owner": npi})]
    verified_lands = [l for l in lands if l.get("verification_status") == "verifiee"]
    disputed_lands = [l for l in lands if l.get("dispute_flag")]

    # 3. Récoltes déclarées
    harvests = [h async for h in db["harvests"].find({"npi_owner": npi}).sort("created_at", -1).limit(10)]

    # 4. Alertes sanitaires / phytosanitaires déclarées
    phyto_alerts = await db["phytosanitary_alerts"].count_documents({"npi": npi})
    health_alerts = await db["farmer_health_alerts"].count_documents({"npi": npi})

    return {
        "npi": npi,
        "performance_score": perf.get("score", 50.0),
        "performance_eligible": perf.get("eligible", True),
        "ineligibility_reasons": perf.get("ineligibility_reasons", []),
        "seasons_count": perf.get("stats", {}).get("seasons", 0),
        "total_lands": len(lands),
        "verified_lands": len(verified_lands),
        "disputed_lands": len(disputed_lands),
        "verified_surface_ha": sum(l.get("surface_hectares", 0.0) for l in verified_lands),
        "harvests_count": len(harvests),
        "phyto_alerts_count": phyto_alerts,
        "health_alerts_count": health_alerts,
        "lands_summary": [
            {
                "id": str(l["_id"]),
                "title": l.get("title", "Parcelle sans titre"),
                "commune": l.get("commune"),
                "department": l.get("department"),
                "surface_ha": l.get("surface_hectares", 1.0),
                "verified": l.get("verification_status") == "verifiee",
                "in_dispute": bool(l.get("dispute_flag")),
            }
            for l in lands
        ],
    }


def _fallback_financial_evaluation(
    offer: dict[str, Any],
    payload: ApplicationCreate,
    farmer_ctx: dict[str, Any],
) -> FinancialAiEvaluation:
    """Moteur d'évaluation financière et de risque expert basé sur les ratios agronomiques béninois."""
    offer_type = offer.get("type", "credit")
    amount_req = payload.amount_requested
    surface = payload.surface_ha
    crop = payload.crop_type

    benchmark = CROP_BENCHMARKS.get(crop, DEFAULT_CROP_BENCHMARK)
    est_yield_kg = payload.declared_harvest_estimate_kg or (surface * benchmark["yield_ha"])
    est_revenue_fcfa = est_yield_kg * benchmark["price_kg"]

    perf_score = farmer_ctx.get("performance_score", 50.0)
    has_dispute = farmer_ctx.get("disputed_lands", 0) > 0
    verified_lands = farmer_ctx.get("verified_lands", 0)

    strengths = []
    risks = []
    conditions = []
    type_metrics = {}

    if verified_lands > 0:
        strengths.append(f"Exploitant titulaire de {verified_lands} parcelle(s) vérifiée(s) par les services cadastraux.")
    else:
        risks.append("Aucune parcelle vérifiée par les agents de l'État : risque foncier modéré.")
        conditions.append("Prévoir une vérification préalable sur le terrain par l'agent territorial.")

    if perf_score >= 60:
        strengths.append(f"Score de performance agricole solide ({perf_score}/100) supérieur à la moyenne des pairs.")
    elif perf_score < 40:
        risks.append(f"Score de performance agricole en retrait ({perf_score}/100) nécessitant un encadrement technique.")

    if has_dispute:
        risks.append("Présence d'un litige foncier en cours sur le patrimoine de l'exploitant.")
        conditions.append("Résolution impérative de tout conflit foncier avant le déboursement final.")

    if offer_type == "credit":
        # Analyse de capacité de remboursement et ratio d'endettement
        debt_service_ratio = (amount_req / est_revenue_fcfa) if est_revenue_fcfa > 0 else 1.5
        interest_rate = offer.get("interest_rate_pct", 5.0)
        repayment_with_interest = amount_req * (1 + (interest_rate or 0) / 100)
        solvency_ratio = (est_revenue_fcfa / repayment_with_interest) if repayment_with_interest > 0 else 0

        type_metrics = {
            "est_revenue_fcfa": round(est_revenue_fcfa, 0),
            "debt_to_revenue_ratio": round(debt_service_ratio, 2),
            "solvency_coverage_ratio": round(solvency_ratio, 2),
            "est_yield_kg": round(est_yield_kg, 0),
        }

        # Calcul du score de crédit (0 - 100)
        base_score = perf_score * 0.45
        if debt_service_ratio <= 0.40:
            base_score += 45
            strengths.append(f"Excellente capacité de remboursement : le crédit représente {round(debt_service_ratio * 100)} % de la récolte prévisionnelle.")
        elif debt_service_ratio <= 0.70:
            base_score += 30
            strengths.append(f"Capacité de remboursement viable : le prêt représente {round(debt_service_ratio * 100)} % de la valeur attendue de la récolte.")
        else:
            base_score += 10
            risks.append(f"Pression financière élevée : montant demandé équivalent à {round(debt_service_ratio * 100)} % des revenus prévisionnels.")
            conditions.append("Réduire le montant ou exiger une caution solidaire d'un groupement de producteurs.")

        if has_dispute:
            base_score -= 30

        final_score = max(5.0, min(95.0, base_score))

        if final_score >= 65 and not has_dispute:
            verdict = "favorable"
            verdict_label = "Avis Favorable - Dossier Solvable"
            rec_amount = amount_req
            summary = (
                f"L'exploitant présente une assise agricole fiable avec un potentiel de production évalué à {est_revenue_fcfa:,.0f} FCFA. "
                "Le ratio d'endettement est maîtrisé et compatible avec les critères de la politique de crédit agricole."
            )
            farmer_advice = (
                f"Votre dossier est jugé très favorable pour la culture du {crop}. Veillez à respecter les dates de semis recommandées "
                "et conservez les factures d'intrants pour le suivi."
            )
        elif final_score >= 45 and not has_dispute:
            verdict = "favorable_sous_conditions"
            verdict_label = "Avis Favorable sous Réserves / Conditions"
            rec_amount = min(amount_req, est_revenue_fcfa * 0.50)
            conditions.append(f"Plafonner le premier déboursement à {rec_amount:,.0f} FCFA avec libération du solde après constat de levée.")
            summary = (
                f"Le projet est pertinent mais présente une exposition financière modérée. Un octroi conditionné à un montant ajusté "
                f"de {rec_amount:,.0f} FCFA et un suivi d'étape est préconisé."
            )
            farmer_advice = (
                f"Votre demande peut être financée avec un accompagnement spécifique. Nous suggérons un déblocage échelonné pour sécuriser "
                "vos investissements en semences et engrais."
            )
        else:
            verdict = "defavorable"
            verdict_label = "Avis Défavorable - Risque Élevé"
            rec_amount = min(amount_req * 0.4, est_revenue_fcfa * 0.3)
            summary = (
                "Le ratio risque/rendement est trop élevé dans la configuration actuelle (surendettement potentiel ou fragilité foncière). "
                "Un réaménagement du plan de culture est requis avant réexamen."
            )
            farmer_advice = (
                "Le montant sollicité dépasse la capacité de couverture de votre récolte actuelle. Rapprochez-vous de votre conseiller communal "
                "pour ajuster la surface ou diversifier les spéculations."
            )

    elif offer_type == "assurance":
        # Analyse de risque indiciel et climatique
        flood_risk_depts = ["Mono", "Couffo", "Ouémé", "Alibori"]
        drought_risk_depts = ["Atacora", "Donga", "Borgou", "Collines"]
        farmer_dept = payload.land_id or "Bénin"

        vuln_index = "moderee"
        if any(d in offer.get("eligible_departments", []) for d in flood_risk_depts):
            vuln_index = "elevee (inondation)"
        elif any(d in offer.get("eligible_departments", []) for d in drought_risk_depts):
            vuln_index = "elevee (sécheresse)"

        type_metrics = {
            "insured_capital_est": round(amount_req, 0),
            "insured_crop": crop,
            "surface_ha": surface,
            "climate_vulnerability": vuln_index,
            "recommended_deductible_pct": 10 if perf_score >= 50 else 15,
        }

        base_score = 50 + (perf_score * 0.35)
        if verified_lands > 0:
            base_score += 15
            strengths.append("Limites parcellaires géoréférencées facilitant la constatation satellitaire des sinistres.")
        if has_dispute:
            base_score -= 25

        final_score = max(10.0, min(95.0, base_score))

        if final_score >= 60 and not has_dispute:
            verdict = "favorable"
            verdict_label = "Souscription Recommandée"
            rec_amount = amount_req
            conditions.append("Enregistrement des coordonnées GPS de la parcelle pour le suivi indiciel par satellite.")
            summary = (
                f"Le profil présente une éligibilité satisfaisante pour la couverture indicielle {offer['title']}. "
                "La régularité des cycles culturaux de l'exploitant limite le risque d'aléa moral."
            )
            farmer_advice = (
                f"Votre parcelle de {crop} ({surface} ha) est bien éligible à l'assurance. En cas de retard de pluviométrie, "
                "l'indemnisation indicielle sera calculée automatiquement selon les données météo officielles."
            )
        else:
            verdict = "favorable_sous_conditions"
            verdict_label = "Souscription sous Conditions"
            rec_amount = amount_req
            conditions.append("Application d'une franchise de 15 % et validation des dates limites de semis.")
            summary = "Souscription possible sous réserve d'application d'une franchise ajustée et d'un contrôle de délimitation."
            farmer_advice = "Assurance accordable avec engagement de respecter le calendrier cultural officiel du MAEP."

    else:
        # Financement / Subvention d'État (FNDA, MAEP)
        is_priority_crop = crop in ["Riz", "Maïs", "Soja", "Maraîchage", "Coton", "Ananas"]
        type_metrics = {
            "strategic_crop_priority": "Filière prioritaire PAG" if is_priority_crop else "Culture secondaire",
            "leverage_multiplier": round(est_revenue_fcfa / amount_req, 2) if amount_req > 0 else 1.0,
            "surface_ha": surface,
        }

        base_score = perf_score * 0.40 + (25 if is_priority_crop else 10) + (15 if verified_lands > 0 else 5)
        if has_dispute:
            base_score -= 30

        final_score = max(10.0, min(95.0, base_score))

        if final_score >= 60 and not has_dispute:
            verdict = "favorable"
            verdict_label = "Attribution Recommandée (Haute Priorité)"
            rec_amount = amount_req
            strengths.append(f"Parfait alignement avec les filières d'intervention prioritaires de la stratégie agricole nationale ({crop}).")
            conditions.append("Signature de la convention d'objectifs de rendement avec l'ATDA du pôle de développement.")
            summary = (
                f"Dossier à fort impact économique et social. L'effet de levier prévisionnel est estimé à "
                f"{type_metrics['leverage_multiplier']} × la subvention allouée."
            )
            farmer_advice = (
                "Votre projet s'inscrit au cœur des priorités gouvernementales de souveraineté alimentaire. "
                "Maintenez une traçabilité rigoureuse de vos récoltes pour bénéficier des tranches suivantes."
            )
        else:
            verdict = "favorable_sous_conditions"
            verdict_label = "Attribution sous Réserve d'Accord Technique"
            rec_amount = min(amount_req, offer.get("amount_max", amount_req))
            conditions.append("Visite de cadrage obligatoire par l'agent de vulgarisation communal.")
            summary = "Subvention envisageable sous réserve d'une revue technique de dimensionnement du projet sur le terrain."
            farmer_advice = "Votre demande sera revue conjointement avec l'agent d'appui agricole de votre commune."

    return FinancialAiEvaluation(
        score=round(final_score, 1),
        verdict=verdict,
        verdict_label=verdict_label,
        strengths=strengths,
        risks=risks,
        recommended_conditions=conditions,
        recommended_amount=rec_amount,
        summary=summary,
        farmer_advice=farmer_advice,
        type_specific_metrics=type_metrics,
    )


async def evaluate_application_with_ai(
    db,
    offer: dict[str, Any],
    payload: ApplicationCreate,
    farmer_ctx: dict[str, Any],
    farmer_npi: str,
) -> FinancialAiEvaluation:
    """Analyse l'éligibilité et le risque avec Gemini, ou bascule sur l'algorithme expert agronomique."""
    prompt = (
        "Tu es un analyste financier et spécialiste en crédit agricole, assurance indicielle et subventions d'État au Bénin (FNDA / MAEP).\n"
        "Évalue la candidature d'un exploitant agricole pour un produit financier selon les spécificités béninoises.\n\n"
        f"--- PRODUIT FINANCIER SOLLICITÉ ---\n"
        f"- Titre : {offer['title']}\n"
        f"- Type : {offer['type']} (credit, assurance ou financement)\n"
        f"- Institution : {offer['institution']}\n"
        f"- Montant demandé : {payload.amount_requested:,.0f} FCFA (Fourchette offre : {offer['amount_min']:,.0f} à {offer['amount_max']:,.0f} FCFA)\n"
        f"- Taux / Prime : Taux intérêt={offer.get('interest_rate_pct')} %, Prime={offer.get('premium_rate_pct')} %, Subvention={offer.get('subsidy_pct')} %\n\n"
        f"--- PROFIL DE L'EXPLOITANT ---\n"
        f"- Score de performance agricole officiel : {farmer_ctx.get('performance_score')}/100\n"
        f"- Saisons enregistrées : {farmer_ctx.get('seasons_count')}\n"
        f"- Parcelles totales : {farmer_ctx.get('total_lands')} (dont {farmer_ctx.get('verified_lands')} vérifiées par un agent)\n"
        f"- Litiges fonciers en cours : {farmer_ctx.get('disputed_lands')}\n"
        f"- Récoltes passées enregistrées : {farmer_ctx.get('harvests_count')}\n\n"
        f"--- DEMANDE SPÉCIFIQUE ---\n"
        f"- Culture ciblée : {payload.crop_type}\n"
        f"- Surface concernée : {payload.surface_ha} hectares\n"
        f"- Récolte estimée déclarée : {payload.declared_harvest_estimate_kg or 'Non spécifiée'} kg\n"
        f"- Descriptif du projet : {payload.project_description}\n"
        f"- Garanties / Remboursement proposés : {payload.guarantees_or_notes or 'Aucune garantie explicite'}\n\n"
        "Consignes d'évaluation impératives :\n"
        "1. Calcule un score global objectif entre 0 et 100.\n"
        "2. Détermine le verdict : 'favorable', 'favorable_sous_conditions', ou 'defavorable'.\n"
        "3. Fournis 2 à 4 forces solides du dossier.\n"
        "4. Identifie 1 à 3 risques réels ou points d'attention (climat, dette, foncier, volatilité des prix).\n"
        "5. Fixe 2 à 3 conditions ou garanties recommandées pour l'agent de l'État / le banquier.\n"
        "6. Recommande un montant adapté (en FCFA).\n"
        "7. Rédige un résumé exécutif clair pour l'agent de validation et un conseil encourageant pour le producteur."
    )

    try:
        evaluation, _ = await ai_service.generate(
            db,
            purpose="financial_risk_scoring",
            schema=FinancialAiEvaluation,
            prompt=prompt,
            requested_by=farmer_npi,
            temperature=0.2,
        )
        return evaluation
    except Exception as exc:
        logger.warning("Évaluation financière IA Gemini indisponible (%s), bascule sur l'algorithme expert de secours", exc)
        return _fallback_financial_evaluation(offer, payload, farmer_ctx)
