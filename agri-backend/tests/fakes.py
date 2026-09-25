"""Faux Gemini (réponse selon le schéma demandé) et faux services externes, pour les tests."""
from types import SimpleNamespace

from app.modules.agronomy.router import FertilizationPlan
from app.modules.assistant.router import AssistantAnswer, Transcript
from app.modules.domains.planning_schemas import ApplicationReview, ValorizationPlan
from app.modules.insights.router import ConcessionReview, DisputeSummary, WeeklyReport
from app.modules.market.router import OfferDraft
from app.modules.monitoring.router import FollowUpAnswer
from app.modules.monitoring.schemas import DiagnosisResult
from app.modules.storage.router import StorageAdvice

R = {"low": 1000, "high": 2000}


def plan() -> ValorizationPlan:
    scenario = {
        "name": "Rotation maïs-soja", "orientation": "mixte", "crops": ["Maïs", "Soja"], "rotation": "maïs puis soja",
        "surface_allocation": [{"crop": "Maïs", "share_pct": 60}, {"crop": "Soja", "share_pct": 40}],
        "yields": [{"crop": "Maïs", "yield_kg_ha": {"low": 2500, "high": 1800}}, {"crop": "Soja", "yield_kg_ha": {"low": 900, "high": 1300}}],
        "costs_fcfa_ha": {"low": 250000, "high": 350000}, "revenue_fcfa_ha": {"low": 450000, "high": 650000},
        "investments": ["Forage"], "labor_needs": "4 actifs", "advantages": ["Soja soutenu par l'État"], "drawbacks": ["Besoin de semences"],
        "calendar": [{"period": "avril - mai", "activity": "Semis du maïs", "details": ""}],
    }
    return ValorizationPlan.model_validate({
        "summary": "Terre apte aux céréales et légumineuses.", "scenarios": [scenario, {**scenario, "name": "Vivrier"}],
        "recommended_scenario_index": 7, "recommendation_rationale": "Meilleure marge",
        "suitability": [{"crop": "Maïs", "suitability": "elevee", "score": 8, "reasons": ["Sol profond"]},
                        {"crop": "Soja", "suitability": "elevee", "score": 7.5, "reasons": ["pH correct"]}],
        "fertility_plan": [{"action": "Chaulage léger", "timing": "avant semis", "rationale": "pH acide"}],
        "risks": [{"risk": "Poche sèche", "likelihood": "moyen", "mitigation": "Paillage"}],
        "valorization_indicators": [{"indicator": "Surface cultivée", "target": "80 %", "deadline_months": 12, "how_to_check": "Relevé GPS"}],
        "data_gaps": ["Pas d'analyse de laboratoire"], "confidence": "moyenne",
    })


FACTORIES = {
    ValorizationPlan: plan,
    ApplicationReview: lambda: ApplicationReview(alignment="fort", strengths=["Expérience"], gaps=[], risks=[], questions_for_interview=["Main-d'œuvre ?"],
                                                 yield_assessment="Cohérent", comment="Dossier solide"),
    FertilizationPlan: lambda: FertilizationPlan(
        simple_summary="Mettez du compost, puis un peu d'engrais.", soil_diagnosis=[{"parameter": "pH", "level": "acide", "comment": "Chauler"}],
        amendments=[], organic_inputs=[{"product": "Compost", "dose": "5 t/ha", "timing": "avant semis", "rationale": "Matière organique"}],
        mineral_inputs=[{"product": "NPK 15-15-15", "dose": "150 kg/ha", "timing": "au semis", "rationale": "Base"}],
        rotation_advice="Alterner avec le soja", expected_yield_kg_ha=R, cost_estimate_fcfa_ha=R, warnings=[]),
    AssistantAnswer: lambda: AssistantAnswer(covered=True, answer="Faites le tour du champ.", simple_summary="Marchez autour du champ.",
                                             used_sources=["enregistrer-parcelle-gps", "fiche-inventee"]),
    Transcript: lambda: Transcript(transcript="Comment enregistrer ma parcelle avec le GPS ?", language_detected="fr"),
    DisputeSummary: lambda: DisputeSummary(neutral_summary="Deux parcelles se chevauchent.", chronology=["Ouverture"], established_facts=["Chevauchement"],
                                           points_of_contention=["Limite"], missing_information=["Acte"], mediation_questions=["Depuis quand ?"],
                                           suggested_next_steps=["Bornage"]),
    WeeklyReport: lambda: WeeklyReport(title="Semaine", highlights=["RAS"], sanitary_situation="Calme", land_situation="Stable",
                                       market_situation="Stable", priority_actions=[{"action": "Inspecter", "zone": "Dangbo", "reason": "Foyer"}], watch_points=[]),
    ConcessionReview: lambda: ConcessionReview(assessment="a_surveiller", findings=["Retard"], early_warnings=["Pluie"], recommended_actions=["Visite"],
                                               next_inspection_focus=["Surface"]),
    StorageAdvice: lambda: StorageAdvice(simple_summary="Séchez le maïs.", immediate_actions=["Sécher"], check_schedule="Toutes les 2 semaines",
                                         sell_or_store="vendre_en_partie", sell_or_store_reasoning="Risque moyen", warrantage_note="Possible", warnings=[]),
    FollowUpAnswer: lambda: FollowUpAnswer(answer="Oui, recommencez après la pluie.", simple_summary="Recommencez après la pluie.", see_advisor=False),
    OfferDraft: lambda: OfferDraft(product_name="Maïs blanc", quality_description="Grains secs", listing_text="Maïs blanc sec, bien trié.", quality_warnings=[]),
    DiagnosisResult: lambda: DiagnosisResult(crop_identified="Maïs", health_status="Maladie", disease_name="Striure", severity="Moyenne",
                                             simple_summary="Maladie des feuilles.", treatment_steps=["Arracher"], treatment_advice="Arracher.", confidence_score=0.7),
}


class FakeGemini:
    def __init__(self):
        self.calls = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self.generate))

    async def generate(self, **kw):
        config = kw.get("config")
        self.calls.append(kw)
        if getattr(config, "response_modalities", None):
            part = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x00\x10" * 24000))
            return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])
        obj = FACTORIES[config.response_schema]()
        return SimpleNamespace(parsed=obj, text=obj.model_dump_json())

    def prompts(self, purpose_schema=None):
        return [c["contents"][0] for c in self.calls if purpose_schema is None or c["config"].response_schema is purpose_schema]


def fake_external():
    """Répond comme iSDAsoil, Open-Meteo (archives, altitude) et Overpass."""
    calls = []

    async def request_json(method, url, *, params=None, data=None, headers=None, timeout=20):
        calls.append(url)
        if url.endswith("/login"):
            return {"access_token": "jeton"}
        if "soilproperty" in url:
            def prop(v, lo, hi, unit=None):
                return [{"value": {"value": v, "unit": unit}, "uncertainty": [{"confidence_interval": "50%", "lower_bound": lo, "upper_bound": hi},
                                                                              {"confidence_interval": "68%", "lower_bound": lo, "upper_bound": hi}]}]
            return {"property": {"ph": prop(5.1, 4.8, 5.4), "carbon_organic": prop(8.0, 6, 10, "g/kg"),
                                 "phosphorous_extractable": prop(9.0, 2, 20, "ppm"), "clay_content": prop(22, 18, 26, "%")}}
        if "archive" in url:
            days = [f"{y}-{m:02d}-{d:02d}" for y in range(2016, 2026) for m in range(1, 13) for d in range(1, 29)]
            rain = [8.0 if int(x[5:7]) in (4, 5, 6, 7, 9, 10) and int(x[8:10]) % 2 else 0.0 for x in days]
            return {"daily": {"time": days, "precipitation_sum": rain, "temperature_2m_max": [33.0] * len(days), "temperature_2m_min": [23.0] * len(days)}}
        if "elevation" in url:
            n = len(params["latitude"].split(","))
            return {"elevation": [20.0] + [21.0 + (i % 3) for i in range(n - 1)]}
        if "overpass" in url or "interpreter" in url:
            return {"elements": [{"tags": {"highway": "secondary", "name": "RNIE1"}, "geometry": [{"lat": 6.70, "lon": 2.44}, {"lat": 6.72, "lon": 2.44}]},
                                 {"tags": {"waterway": "river", "name": "Ouémé"}, "geometry": [{"lat": 6.70, "lon": 2.47}, {"lat": 6.71, "lon": 2.47}]}]}
        raise AssertionError(f"URL inattendue : {url}")

    return request_json, calls
