from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_financial_catalog
from backend.app.financial_catalog.loader import load_curated_catalog
from backend.app.main import app


CATALOG_ROOT = Path(__file__).resolve().parents[2] / "config/financial_catalog"
CATALOG = load_curated_catalog(CATALOG_ROOT)


def _client() -> TestClient:
    app.dependency_overrides[get_financial_catalog] = lambda: CATALOG
    return TestClient(app)


def test_finance_plan_api_contract() -> None:
    try:
        with _client() as client:
            response = client.post("/api/v1/finance/plans", json={
                "candidate": {
                    "deposit_krw": 20_000_000,
                    "monthly_rent_krw": 1_000_000,
                    "management_fee_krw": 100_000,
                    "key_money_krw": 0,
                },
                "additional_costs": {"interior_krw": 10_000_000},
                "eligibility": {
                    "own_capital_krw": 25_000_000,
                    "business_status": "pre_startup",
                    "is_small_business": True,
                    "vulnerability": "unknown",
                    "has_policy_excluded_industry": False,
                },
            })
            assert response.status_code == 200
            body = response.json()
            assert body["request_id"] == response.headers["x-request-id"]
            assert body["funding"]["total_first_year_cash_need_krw"] == 43_200_000
            assert body["funding"]["funding_gap_krw"] == 18_200_000
            assert len(body["policy_candidates"]) == 33
            kb = next(
                item for item in body["policy_candidates"]
                if item["program_id"] == "kb-owner-plus-credit-line"
            )
            assert kb["product_type"] == "bank_loan"
            assert kb["benefits"][0]["amount_max_krw"] == 100_000_000
    finally:
        app.dependency_overrides.pop(get_financial_catalog, None)


def test_operating_finance_plan_requires_business_age() -> None:
    try:
        with _client() as client:
            response = client.post("/api/v1/finance/plans", json={
                "candidate": {
                    "deposit_krw": 0, "monthly_rent_krw": 0,
                    "management_fee_krw": 0, "key_money_krw": 0,
                },
                "eligibility": {"own_capital_krw": 0, "business_status": "operating"},
            })
            assert response.status_code == 422
            assert "업력" in response.json()["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_financial_catalog, None)


def test_finance_plan_does_not_treat_missing_lease_cost_as_zero() -> None:
    try:
        with _client() as client:
            response = client.post("/api/v1/finance/plans", json={
                "candidate": {
                    "deposit_krw": 10_000_000,
                    "monthly_rent_krw": 1_000_000,
                    "key_money_krw": 0,
                },
                "eligibility": {"own_capital_krw": 0, "business_status": "pre_startup"},
            })
            assert response.status_code == 422
            assert "management_fee_krw" in response.json()["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_financial_catalog, None)
