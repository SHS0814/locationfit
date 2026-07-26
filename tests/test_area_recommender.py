"""Tests for the weighted-distance area recommender."""

import json
import unittest

import numpy as np
import pandas as pd

from src.models.area_recommender import (
    AreaRecommender,
    EVIDENCE_WEIGHTS,
    RecommendationRequest,
    STRATEGY_GROUP_WEIGHTS,
    build_preference_features,
    score_industry_evidence,
    normalize_performance_weights,
    strategy_evidence_weights,
    validate_request,
    weighted_euclidean_scores,
)


def synthetic_recommender() -> AreaRecommender:
    rows = 15
    index = pd.DataFrame(
        {
            "area_code": [f"a{i:02d}" for i in range(rows)],
            "area_name": [f"상권{i}" for i in range(rows)],
            "district_name": ["강남구" if i < 8 else "마포구" for i in range(rows)],
            "area_type_code": ["A" if i % 2 == 0 else "D" for i in range(rows)],
            "area_type_name": ["골목상권" if i % 2 == 0 else "발달상권" for i in range(rows)],
            "data_reliability": np.linspace(0.8, 1.0, rows),
            "female_floating_ratio": np.linspace(0.2, 0.8, rows),
            "age_20_floating_ratio": np.linspace(0.1, 0.5, rows),
            "time_17_21_floating_ratio": np.linspace(0.1, 0.6, rows),
            "weekend_floating_ratio": np.linspace(0.1, 0.9, rows),
            "log_floating_density": np.linspace(1.0, 5.0, rows),
            "log_resident_density": np.linspace(5.0, 1.0, rows),
            "log_worker_density": np.linspace(1.0, 4.0, rows),
            "log_apartment_household_density": np.linspace(1.0, 3.0, rows),
            "log_apartment_complex_density": np.linspace(1.0, 2.0, rows),
            "log_transport_facility_density": np.linspace(0.0, 2.0, rows),
            "log_education_facility_density": np.linspace(0.0, 2.0, rows),
            "log_medical_facility_density": np.linspace(0.0, 2.0, rows),
            "log_shopping_facility_density": np.linspace(0.0, 2.0, rows),
            "log_culture_facility_density": np.linspace(0.0, 2.0, rows),
            "log_store_density": np.linspace(1.0, 4.0, rows),
            "franchise_ratio": np.linspace(0.0, 0.5, rows),
        }
    )
    evidence = pd.DataFrame(
        {
            "area_code": index["area_code"],
            "industry_code": "i1",
            "industry_name": "테스트업종",
            "data_reliability": np.linspace(0.55, 1.0, rows),
            "reliability_grade": ["D", "A", "C", *("A" for _ in range(rows - 3))],
            "stale_observation_flag": [0, 1, *(0 for _ in range(rows - 2))],
            "current_sales_missing_flag": [0, 1, *(0 for _ in range(rows - 2))],
            "yoy_growth_rate": np.linspace(-0.2, 0.5, rows),
            "recent_4q_growth_rate": np.linspace(-0.1, 0.4, rows),
            "long_term_sales_trend_slope": np.linspace(-0.05, 0.1, rows),
            "sales_coefficient_of_variation": np.linspace(0.8, 0.1, rows),
            "decline_quarter_ratio": np.linspace(0.8, 0.1, rows),
            "competition_intensity": np.linspace(0.8, 0.1, rows),
            "closing_rate": np.linspace(0.2, 0.01, rows),
            "churn_rate": np.linspace(0.3, 0.02, rows),
            "recent_closure_rate_increase": np.linspace(0.1, -0.1, rows),
            "net_store_growth_rate": np.linspace(-0.1, 0.1, rows),
            "recent_4q_average_sales": np.linspace(100, 1000, rows),
            "recent_4q_average_sales_per_store": np.linspace(10, 100, rows),
            "closure_rate_increased_flag": 0,
        }
    )
    return AreaRecommender(index, evidence)


class AreaRecommenderTests(unittest.TestCase):
    def test_performance_weight_normalization_and_validation(self) -> None:
        unit = {
            "scale_productivity": 0.2, "growth": 0.4, "stability": 0.2,
            "competition": 0.05, "closure_risk": 0.15,
        }
        percent = {key: value * 100 for key, value in unit.items()}
        arbitrary = {key: value * 7.3 for key, value in unit.items()}
        self.assertEqual(normalize_performance_weights(unit), unit)
        for supplied in (percent, arbitrary):
            normalized = normalize_performance_weights(supplied)
            self.assertAlmostEqual(sum(normalized.values()), 1.0)
            for key in unit:
                self.assertAlmostEqual(normalized[key], unit[key])

        invalid = [
            {**unit, "growth": -1},
            {key: 0 for key in unit},
            {**unit, "growth": np.nan},
            {**unit, "growth": np.inf},
            {**unit, "unknown": 1},
            {key: value for key, value in unit.items() if key != "growth"},
        ]
        for weights in invalid:
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                normalize_performance_weights(weights)

    def test_default_and_explicit_default_weights_are_identical(self) -> None:
        evidence = synthetic_recommender().evidence
        implicit = score_industry_evidence(evidence, strategy="balanced")
        explicit = score_industry_evidence(
            evidence,
            strategy="balanced",
            performance_group_weights=STRATEGY_GROUP_WEIGHTS["balanced"],
        )
        self.assertTrue(np.allclose(implicit["raw_evidence_score"], explicit["raw_evidence_score"]))

    def test_missing_group_is_renormalized_and_contributions_match_raw_score(self) -> None:
        evidence = synthetic_recommender().evidence.copy()
        evidence.loc[5, ["sales_coefficient_of_variation", "decline_quarter_ratio"]] = np.nan
        weights = {
            "scale_productivity": 20, "growth": 40, "stability": 20,
            "competition": 10, "closure_risk": 10,
        }
        scored = score_industry_evidence(evidence, performance_group_weights=weights)
        breakdown = scored.loc[5, "performance_breakdown"]
        self.assertFalse(breakdown["stability"]["available"])
        self.assertEqual(breakdown["stability"]["effective_weight"], 0)
        self.assertAlmostEqual(
            sum(group["effective_weight"] for group in breakdown.values()),
            1.0,
        )
        self.assertAlmostEqual(
            sum(group["contribution"] for group in breakdown.values()),
            scored.loc[5, "raw_evidence_score"],
            places=5,
        )

    def test_custom_growth_and_risk_weights_change_conflicting_scores(self) -> None:
        evidence = synthetic_recommender().evidence.copy()
        for metric in EVIDENCE_WEIGHTS:
            evidence[metric] = 0.5
        evidence.loc[3, ["yoy_growth_rate", "recent_4q_growth_rate", "long_term_sales_trend_slope", "net_store_growth_rate"]] = 1.0
        evidence.loc[3, ["closing_rate", "churn_rate", "recent_closure_rate_increase"]] = 1.0
        evidence.loc[4, ["yoy_growth_rate", "recent_4q_growth_rate", "long_term_sales_trend_slope", "net_store_growth_rate"]] = 0.0
        evidence.loc[4, ["closing_rate", "churn_rate", "recent_closure_rate_increase"]] = 0.0
        growth = score_industry_evidence(evidence, performance_group_weights={
            "scale_productivity": 0, "growth": 1, "stability": 0,
            "competition": 0, "closure_risk": 0,
        })
        risk = score_industry_evidence(evidence, performance_group_weights={
            "scale_productivity": 0, "growth": 0, "stability": 0,
            "competition": 0, "closure_risk": 1,
        })
        self.assertGreater(growth.loc[3, "raw_evidence_score"], growth.loc[4, "raw_evidence_score"])
        self.assertLess(risk.loc[3, "raw_evidence_score"], risk.loc[4, "raw_evidence_score"])

    def test_user_input_validation(self) -> None:
        validate_request(RecommendationRequest(industry_code="i1"), valid_industries={"i1"})
        with self.assertRaisesRegex(ValueError, "존재하지 않는"):
            validate_request(
                RecommendationRequest(industry_code="missing", weekend_importance=1.0),
                valid_industries={"i1"},
            )

    def test_industry_only_request_keeps_all_optional_conditions_unrestricted(self) -> None:
        engine = synthetic_recommender()
        result = engine.recommend(
            RecommendationRequest(industry_code="i1", top_n=3),
            k=10,
        )

        self.assertEqual(result.preference_features, ())
        self.assertTrue(result.recommendations["condition_fit_score"].eq(100).all())
        self.assertEqual(result.diagnostics["condition_feature_count"], 0)

    def test_condition_mapping_uses_explicit_features_only(self) -> None:
        request = RecommendationRequest(
            industry_code="i1",
            target_gender="female",
            target_age_groups=("20",),
            weekend_importance=0.8,
        )
        available = {"female_floating_ratio", "age_20_floating_ratio", "weekend_floating_ratio"}
        mappings = build_preference_features(request, available)
        self.assertEqual({mapping.feature for mapping in mappings}, available)
        self.assertNotIn("male_floating_ratio", {mapping.feature for mapping in mappings})

    def test_weighted_distance_and_score_bounds(self) -> None:
        values = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
        distance, score = weighted_euclidean_scores(values, np.array([2.0, 2.0]), np.array([1.0, 2.0]))
        self.assertEqual(int(np.argmax(score)), 2)
        self.assertTrue(np.all((score >= 0) & (score <= 100)))
        self.assertEqual(distance[2], 0)

    def test_evidence_score_directionality_and_reliability_penalty(self) -> None:
        engine = synthetic_recommender()
        scored = score_industry_evidence(engine.evidence)
        best = scored.iloc[-1]
        worst = scored.iloc[0]
        self.assertGreater(best["raw_evidence_score"], worst["raw_evidence_score"])
        c_row = scored.loc[scored["reliability_grade"].eq("C")].iloc[0]
        self.assertAlmostEqual(
            c_row["reliability_adjusted_evidence_score"],
            c_row["evidence_score_shrinkage"] * 0.9,
        )

    def test_strategy_weights_and_semantic_direction(self) -> None:
        engine = synthetic_recommender()
        evidence = engine.evidence.copy()
        for metric in EVIDENCE_WEIGHTS:
            evidence[metric] = 0.5
        growth_metrics = [
            "yoy_growth_rate", "recent_4q_growth_rate",
            "long_term_sales_trend_slope", "net_store_growth_rate",
        ]
        risk_metrics = [
            "sales_coefficient_of_variation", "decline_quarter_ratio",
            "closing_rate", "churn_rate", "recent_closure_rate_increase",
        ]
        evidence.loc[3, growth_metrics] = 1.0
        evidence.loc[3, risk_metrics] = 1.0
        evidence.loc[4, growth_metrics] = 0.0
        evidence.loc[4, risk_metrics] = 0.0

        growth = score_industry_evidence(evidence, strategy="growth")
        stability = score_industry_evidence(evidence, strategy="stability")

        self.assertAlmostEqual(sum(weight for weight, _ in strategy_evidence_weights("growth").values()), 1.0)
        self.assertGreater(growth.loc[3, "raw_evidence_score"], growth.loc[4, "raw_evidence_score"])
        self.assertGreater(stability.loc[4, "raw_evidence_score"], stability.loc[3, "raw_evidence_score"])

    def test_nan_sales_is_not_converted_to_zero(self) -> None:
        engine = synthetic_recommender()
        engine.evidence.loc[0, "recent_4q_average_sales"] = np.nan
        scored = score_industry_evidence(engine.evidence)
        self.assertTrue(np.isnan(scored.loc[0, "recent_4q_average_sales"]))
        self.assertTrue(np.isnan(scored.loc[0, "evidence_component_recent_4q_average_sales"]))

    def test_hard_filter_D_stale_exclusion_and_explanations(self) -> None:
        engine = synthetic_recommender()
        request = RecommendationRequest(
            industry_code="i1",
            preferred_districts=("마포구",),
            target_gender="female",
            floating_population_importance=1.0,
            top_n=3,
        )
        result = engine.recommend(request, k=10)
        output = result.recommendations
        self.assertTrue(output["district_name"].eq("마포구").all())
        self.assertTrue(output["reliability_grade"].ne("D").all())
        self.assertTrue(output["stale_flag"].eq(0).all())
        self.assertTrue(output["final_score"].between(0, 100).all())
        reasons = json.loads(output.iloc[0]["positive_reasons"])
        self.assertGreaterEqual(len(reasons), 1)
        self.assertIn("feature", reasons[0])

    def test_same_input_is_deterministic(self) -> None:
        engine = synthetic_recommender()
        request = RecommendationRequest(
            industry_code="i1",
            weekend_importance=1.0,
            resident_population_importance=0.5,
            top_n=5,
        )
        first = engine.recommend(request, k=10).recommendations
        second = engine.recommend(request, k=10).recommendations
        self.assertEqual(first["area_code"].tolist(), second["area_code"].tolist())
        self.assertTrue(np.allclose(first["final_score"], second["final_score"]))

    def test_custom_weights_are_reported_in_diagnostics(self) -> None:
        engine = synthetic_recommender()
        request = RecommendationRequest(
            industry_code="i1",
            top_n=3,
            performance_group_weights={
                "scale_productivity": 20, "growth": 40, "stability": 20,
                "competition": 5, "closure_risk": 15,
            },
        )
        result = engine.recommend(request, k=10)
        self.assertEqual(result.diagnostics["performance_weights_source"], "user_custom")
        self.assertAlmostEqual(sum(result.diagnostics["performance_group_weights"].values()), 1.0)
        for _, row in result.recommendations.iterrows():
            breakdown = row["performance_breakdown"]
            self.assertAlmostEqual(
                sum(group["contribution"] for group in breakdown.values()),
                row["raw_evidence_score"],
                places=5,
            )


if __name__ == "__main__":
    unittest.main()
