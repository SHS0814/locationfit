from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.schemas.recommendation import RecommendationRequestSchema
from backend.app.services.recommender_service import RecommenderService


ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts/current"


def test_metadata_and_recommendation_with_real_artifacts() -> None:
    service = RecommenderService(ARTIFACT_DIR)
    metadata = service.metadata()
    assert len(metadata["industries"]) == 63
    assert "강남구" in metadata["districts"]
    assert len(service.district_boundaries) == 25
    assert set(service.district_boundaries) == set(metadata["districts"])
    assert metadata["performance_weight_presets"]["balanced"]["growth"] == 0.27

    geography = service.market_geographies(
        group_by="district",
        entity_keys=["강남구", "마포구"],
    )
    assert [item["entity_key"] for item in geography] == ["강남구", "마포구"]
    assert all(item["boundary"]["type"] in {"Polygon", "MultiPolygon"} for item in geography)

    request = RecommendationRequestSchema(
        industry_code="CS100001",
        target_age_groups=["20", "30"],
        floating_population_importance=0.7,
        top_n=5,
    )
    recommendations, diagnostics = service.recommend(request)
    assert len(recommendations) == 5
    assert diagnostics["returned"] == 5
    assert all(37.0 < item["latitude"] < 38.0 for item in recommendations)
    assert all(126.0 < item["longitude"] < 128.0 for item in recommendations)
    assert all(item["area_size_sqm"] > 0 for item in recommendations)
    assert all(item["boundary"]["type"] in {"Polygon", "MultiPolygon"} for item in recommendations)
    assert all(item["boundary"]["coordinates"] for item in recommendations)
    assert isinstance(recommendations[0]["positive_reasons"], list)
    assert set(recommendations[0]["performance_breakdown"]) == {
        "scale_productivity", "growth", "stability", "competition", "closure_risk",
    }
    assert diagnostics["performance_weights_source"] == "strategy_default"


def test_recommendation_report_compares_top_three_with_full_eligible_median() -> None:
    service = RecommenderService(ARTIFACT_DIR)
    request = RecommendationRequestSchema(
        industry_code="CS100001",
        target_age_groups=["20"],
        top_n=5,
    )
    recommendations, diagnostics, report = service.recommend_with_report(request)
    engine_result = service._run_recommendation(request)

    assert [area["area_code"] for area in report["areas"]] == [
        item["area_code"] for item in recommendations[:3]
    ]
    assert report["candidate_count"] == diagnostics["eligible_candidates_before_k"]
    assert report["candidate_count"] == len(engine_result.eligible_candidates)
    assert report["benchmark"]["recent_4q_average_sales"] == pytest.approx(
        engine_result.eligible_candidates["recent_4q_average_sales"].median()
    )
    assert report["benchmark"]["recent_store_count"] == pytest.approx(
        engine_result.eligible_candidates["recent_store_count"].median()
    )
    assert report["benchmark"]["same_industry_store_density"] == pytest.approx(
        engine_result.eligible_candidates["same_industry_store_density"].median()
    )
    assert report["areas"][0]["metrics"]["final_score"] == recommendations[0]["final_score"]
    source = engine_result.eligible_candidates.set_index("area_code").loc[recommendations[0]["area_code"]]
    assert report["areas"][0]["metrics"]["recent_store_count"] == source["recent_store_count"]
    assert report["areas"][0]["metrics"]["same_industry_store_density"] == pytest.approx(
        source["same_industry_store_density"]
    )
    assert "competition_intensity" not in report["areas"][0]["metrics"]
    assert report["competition_reference_period"] == "2025Q4"
    assert report["performance_weights_source"] == "strategy_default"
    assert report["areas"][0]["performance_breakdown"] == recommendations[0]["performance_breakdown"]

    repeated, repeated_diagnostics = service.recommend(request)
    assert [item["area_code"] for item in repeated] == [item["area_code"] for item in recommendations]
    assert [item["final_score"] for item in repeated] == [item["final_score"] for item in recommendations]
    assert repeated_diagnostics == diagnostics


def test_custom_performance_weights_contract_and_normalization() -> None:
    service = RecommenderService(ARTIFACT_DIR)
    request = RecommendationRequestSchema(
        industry_code="CS100001",
        top_n=3,
        performance_group_weights={
            "scale_productivity": 20,
            "growth": 40,
            "stability": 20,
            "competition": 5,
            "closure_risk": 15,
        },
    )
    recommendations, diagnostics, report = service.recommend_with_report(request)
    assert diagnostics["performance_weights_source"] == "user_custom"
    assert diagnostics["performance_group_weights"] == pytest.approx({
        "scale_productivity": 0.2,
        "growth": 0.4,
        "stability": 0.2,
        "competition": 0.05,
        "closure_risk": 0.15,
    })
    assert report["performance_group_weights"] == diagnostics["performance_group_weights"]
    for item in recommendations:
        assert sum(
            group["contribution"] for group in item["performance_breakdown"].values()
        ) == pytest.approx(item["raw_evidence_score"], abs=1e-5)


@pytest.mark.parametrize("weights", [
    {"scale_productivity": 0, "growth": 0, "stability": 0, "competition": 0, "closure_risk": 0},
    {"scale_productivity": 1, "growth": -1, "stability": 1, "competition": 1, "closure_risk": 1},
    {"scale_productivity": 1, "growth": float("nan"), "stability": 1, "competition": 1, "closure_risk": 1},
    {"scale_productivity": 1, "growth": float("inf"), "stability": 1, "competition": 1, "closure_risk": 1},
    {"scale_productivity": 1, "growth": 1, "stability": 1, "competition": 1},
    {"scale_productivity": 1, "growth": 1, "stability": 1, "competition": 1, "closure_risk": 1, "unknown": 1},
])
def test_custom_performance_weight_validation(weights: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        RecommendationRequestSchema(industry_code="CS100001", performance_group_weights=weights)


def test_recommendation_evidence_context_exposes_sources_methodology_and_limits() -> None:
    service = RecommenderService(ARTIFACT_DIR)
    request = RecommendationRequestSchema(
        industry_code="CS100001",
        target_age_groups=["20"],
        strategy="growth",
        top_n=3,
    )
    _, diagnostics, _ = service.recommend_with_report(request)
    context = service.recommendation_evidence_context(request, diagnostics)

    assert context["artifact_version"] == "2025q4-v3"
    assert context["data_period"]["performance"] == "2021Q1~2025Q4"
    assert {source["dataset_id"] for source in context["sources"]} >= {
        "OA-15572", "OA-15577", "OA-15568",
    }
    assert context["scoring"]["strategy"] == "growth"
    assert context["scoring"]["final_weights"] == {
        "condition_fit_score": 0.45,
        "reliability_adjusted_evidence_score": 0.55,
    }
    assert "실제 개별 점포 매출" in context["limitations"][0]
    assert "성공 확률" in context["limitations"][1]


def test_strategy_scenarios_and_market_landscape_use_real_artifacts() -> None:
    service = RecommenderService(ARTIFACT_DIR)
    request = RecommendationRequestSchema(
        industry_code="CS100001",
        preferred_districts=["강남구"],
        target_age_groups=["20"],
        top_n=5,
    )

    landscape = service.inspect_market_landscape(request)
    scenarios = service.analyze_strategy_scenarios(request)
    tradeoffs, relaxations = service.diagnose_constraint_conflicts(request, scenarios)

    assert landscape["eligible_area_count"] > 0
    assert [item["strategy"] for item in scenarios] == [
        "condition_fit", "growth", "stability",
    ]
    assert all(item["diagnostics"]["policy_version"] == "strategy-v1" for item in scenarios)
    assert isinstance(tradeoffs, list)
    assert all(option["candidate_count_after"] > option["candidate_count_before"] for option in relaxations)
