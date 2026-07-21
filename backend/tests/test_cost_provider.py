from __future__ import annotations

from pathlib import Path
import hashlib
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.schemas.recommendation import RecommendationRequestSchema
from backend.app.services.cost_provider import (
    ParquetCommercialCostProvider,
    calculate_budget_fit,
    calculate_lease_plan,
)
from backend.app.services.recommender_service import RecommenderService
from backend.app.main import app


ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts/current"


def sample_provider(area_codes: list[str]) -> ParquetCommercialCostProvider:
    observations = pd.DataFrame([{
        "area_code": code,
        "area_name": f"테스트 상권 {code}",
        "admin_dong_name": "테스트동",
        "rent_basis_geography": "admin_dong",
        "rent_basis_name": "테스트동",
        "floor": floor,
        "reference_period": "2026Q1",
        "unit_converted_rent_krw_sqm": 50_000.0,
        "annual_conversion_rate": 0.12,
    } for code in area_codes for floor in ("all", "f1")])
    return ParquetCommercialCostProvider(observations)


def test_estimate_budget_fit_and_lease_plan_formulas() -> None:
    provider = sample_provider(["A"])
    estimate = provider.estimate("A", "f1", 60)
    assert estimate is not None
    assert estimate.estimated_converted_monthly_rent_krw == 3_000_000
    assert estimate.admin_dong_name == "테스트동"
    assert estimate.geography_fallback_used is False
    assert calculate_budget_fit(2_400_000, 3_000_000) == 80
    assert calculate_budget_fit(4_000_000, 3_000_000) == 100

    plan = calculate_lease_plan(
        estimate,
        deposit_krw=100_000_000,
        total_startup_budget_krw=200_000_000,
    )
    assert plan.cash_monthly_rent_krw == 2_000_000
    assert plan.annual_cash_rent_krw == 24_000_000
    assert plan.first_year_cash_outlay_krw == 124_000_000
    assert plan.remaining_startup_budget_krw == 76_000_000
    assert plan.deposit_share_of_budget == 0.5


def test_missing_floor_uses_same_period_all_floor_with_disclosure() -> None:
    estimate = sample_provider(["A"]).estimate("A", "non_f1", 33)
    assert estimate is not None
    assert estimate.floor == "non_f1"
    assert estimate.rent_basis_floor == "all"
    assert estimate.fallback_used is True


def test_no_budget_and_total_budget_only_preserve_ranking_and_scores() -> None:
    baseline_service = RecommenderService(ARTIFACT_DIR)
    base = RecommendationRequestSchema(
        industry_code="CS100001", target_age_groups=["20"], top_n=5,
    )
    baseline, baseline_diagnostics = baseline_service.recommend(base)

    cost_service = RecommenderService(
        ARTIFACT_DIR,
        sample_provider(baseline_service.index["area_code"].astype(str).tolist()),
    )
    repeated, repeated_diagnostics = cost_service.recommend(base)
    total_only, total_diagnostics = cost_service.recommend(
        base.model_copy(update={"total_startup_budget_krw": 200_000_000})
    )
    assert [(item["area_code"], item["final_score"]) for item in repeated] == [
        (item["area_code"], item["final_score"]) for item in baseline
    ]
    assert [(item["area_code"], item["final_score"]) for item in total_only] == [
        (item["area_code"], item["final_score"]) for item in baseline
    ]
    assert repeated_diagnostics == baseline_diagnostics == total_diagnostics


def test_monthly_limit_applies_twenty_percent_budget_score_without_filtering() -> None:
    seed = RecommenderService(ARTIFACT_DIR)
    provider = sample_provider(seed.index["area_code"].astype(str).tolist())
    service = RecommenderService(ARTIFACT_DIR, provider)
    request = RecommendationRequestSchema(
        industry_code="CS100001",
        target_age_groups=["20"],
        top_n=5,
        monthly_converted_rent_limit_krw=2_400_000,
        rentable_area_sqm=60,
        floor="f1",
    )
    items, diagnostics = service.recommend(request)
    assert len(items) == 5
    assert diagnostics["budget_adjusted"] is True
    assert all(item["rental_estimate"] is not None for item in items)
    assert all(item["budget_fit_score"] == 80 for item in items)
    assert all(item["final_score"] == pytest.approx(item["base_final_score"] * 0.8 + 16, abs=0.01) for item in items)


def test_report_compares_rent_with_all_eligible_candidate_median() -> None:
    seed = RecommenderService(ARTIFACT_DIR)
    service = RecommenderService(
        ARTIFACT_DIR,
        sample_provider(seed.index["area_code"].astype(str).tolist()),
    )
    request = RecommendationRequestSchema(
        industry_code="CS100001",
        target_age_groups=["20"],
        top_n=3,
        rentable_area_sqm=60,
        floor="f1",
    )
    items, _, report = service.recommend_with_report(request)

    assert report["benchmark"]["estimated_converted_monthly_rent_krw"] == 3_000_000
    assert report["benchmark"]["unit_converted_rent_krw_sqm"] == 50_000
    assert report["areas"][0]["metrics"]["estimated_converted_monthly_rent_krw"] == 3_000_000
    assert report["areas"][0]["metrics"]["unit_converted_rent_krw_sqm"] == 50_000
    assert report["areas"][0]["rental_estimate"] == items[0]["rental_estimate"]
    assert report["rental_estimate_uses_default"] is False


def test_report_shows_default_reference_rent_without_user_rent_input() -> None:
    seed = RecommenderService(ARTIFACT_DIR)
    service = RecommenderService(
        ARTIFACT_DIR,
        sample_provider(seed.index["area_code"].astype(str).tolist()),
    )
    _, _, report = service.recommend_with_report(RecommendationRequestSchema(
        industry_code="CS100001",
        target_age_groups=["20"],
        top_n=3,
    ))

    assert report["rental_estimate_uses_default"] is True
    assert "10평" in report["rental_estimate_basis"]
    assert report["areas"][0]["rental_estimate"] is not None
    assert report["areas"][0]["metrics"]["estimated_converted_monthly_rent_krw"] == pytest.approx(
        50_000 * 33.05785
    )


def test_request_requires_complete_rent_conditions_for_monthly_limit() -> None:
    with pytest.raises(ValueError, match="임대면적"):
        RecommendationRequestSchema(
            industry_code="CS100001",
            target_age_groups=["20"],
            monthly_converted_rent_limit_krw=3_000_000,
        )
    with pytest.raises(ValueError):
        RecommendationRequestSchema.model_validate({
            "industry_code": "CS100001",
            "target_age_groups": ["20"],
            "commercial_property_type": "small_retail",
        })


def test_lease_plan_api_uses_static_provider() -> None:
    recommender = RecommenderService(
        ARTIFACT_DIR,
        sample_provider(["A"]),
    )
    with TestClient(app) as client:
        app.state.recommender = recommender
        response = client.post("/api/v1/commercial-costs/lease-plan", json={
            "area_code": "A",
            "floor": "f1",
            "rentable_area_sqm": 60,
            "deposit_krw": 100_000_000,
            "total_startup_budget_krw": 200_000_000,
        })
    assert response.status_code == 200
    assert response.json()["lease_plan"]["cash_monthly_rent_krw"] == 2_000_000


def test_parquet_loader_verifies_manifest_checksum(tmp_path: Path) -> None:
    provider = sample_provider(["A"])
    observation_path = tmp_path / "commercial_rent_observations.parquet"
    provider.observations.to_parquet(observation_path, index=False)
    files = {
        observation_path.name: {"sha256": hashlib.sha256(observation_path.read_bytes()).hexdigest()}
    }
    (tmp_path / "manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")

    loaded = ParquetCommercialCostProvider.from_artifact_dir(tmp_path)
    assert loaded.estimate("A", "f1", 60) is not None
    observation_path.write_bytes(observation_path.read_bytes() + b"corrupt")
    with pytest.raises(RuntimeError, match="체크섬"):
        ParquetCommercialCostProvider.from_artifact_dir(tmp_path)
