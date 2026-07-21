from fastapi.testclient import TestClient

from backend.app.main import app


def test_finance_plan_api_contract() -> None:
    with TestClient(app) as client:
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
        assert len(body["policy_candidates"]) == 2


def test_operating_finance_plan_requires_business_age() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/finance/plans", json={
            "candidate": {
                "deposit_krw": 0, "monthly_rent_krw": 0,
                "management_fee_krw": 0, "key_money_krw": 0,
            },
            "eligibility": {"own_capital_krw": 0, "business_status": "operating"},
        })
        assert response.status_code == 422
        assert "업력" in response.json()["error"]["message"]


def test_finance_plan_does_not_treat_missing_lease_cost_as_zero() -> None:
    with TestClient(app) as client:
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
