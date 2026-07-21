from __future__ import annotations

import asyncio

from backend.app.schemas.finance import (
    ConfirmedLeaseCandidate,
    FinancePlanRequest,
    FounderEligibility,
    LeaseCandidateExtraction,
    LeaseCandidateExtractRequest,
    StartupAdditionalCosts,
)
from backend.app.services.finance_service import FinancePlanService, calculate_funding
from backend.app.services.listing_service import LeaseCandidateService, _validate_public_url


def request_for(*, vulnerability: str = "unknown", months: int | None = None) -> FinancePlanRequest:
    return FinancePlanRequest(
        candidate=ConfirmedLeaseCandidate(
            address="서울시 중구 테스트로 1",
            deposit_krw=50_000_000,
            monthly_rent_krw=2_000_000,
            management_fee_krw=300_000,
            key_money_krw=10_000_000,
        ),
        additional_costs=StartupAdditionalCosts(
            interior_krw=30_000_000,
            equipment_krw=10_000_000,
            initial_inventory_krw=5_000_000,
            working_capital_krw=15_000_000,
        ),
        eligibility=FounderEligibility(
            own_capital_krw=80_000_000,
            business_status="operating" if months is not None else "pre_startup",
            business_age_months=months,
            is_small_business=True,
            vulnerability=vulnerability,
            has_policy_excluded_industry=False,
        ),
    )


def test_funding_calculation_separates_deposit_and_first_year_costs() -> None:
    result = calculate_funding(request_for())
    assert result["refundable_deposit_krw"] == 50_000_000
    assert result["annual_occupancy_cost_krw"] == 27_600_000
    assert result["additional_startup_cost_krw"] == 60_000_000
    assert result["total_first_year_cash_need_krw"] == 147_600_000
    assert result["funding_gap_krw"] == 67_600_000
    assert result["own_capital_ratio"] == 0.542


def test_policy_matching_is_deterministic_and_does_not_promise_approval() -> None:
    result = FinancePlanService().create_plan(request_for(vulnerability="low_credit", months=6))
    assert [item["status"] for item in result["policy_candidates"]] == ["needs_review", "basic_fit"]
    assert result["policy_candidates"][1]["name"] == "미소금융 운영자금"
    assert "심사" in result["disclosure"]


def test_operating_fund_requires_three_months() -> None:
    result = FinancePlanService().create_plan(request_for(vulnerability="low_credit", months=2))
    assert result["policy_candidates"][1]["status"] == "not_eligible"


class FakeRunner:
    def __init__(self) -> None:
        self.source = ""

    async def run(self, source: str) -> LeaseCandidateExtraction:
        self.source = source
        return LeaseCandidateExtraction(
            address="서울시 중구 테스트로 1",
            deposit_krw=50_000_000,
            monthly_rent_krw=2_000_000,
            missing_fields=["management_fee_krw", "key_money_krw", "rentable_area_sqm", "floor"],
        )


def test_pasted_listing_is_extracted_without_fetching_url() -> None:
    runner = FakeRunner()
    service = LeaseCandidateService(runner, timeout_seconds=1)
    result = asyncio.run(service.extract(LeaseCandidateExtractRequest(
        source_url="https://example.com/listing/1",
        source_text="보증금 5천만원, 월세 200만원",
        selected_area_name="명동",
    )))
    assert result["source_kind"] == "url_and_text"
    assert result["requires_confirmation"] is True
    assert "명동" in runner.source


def test_private_and_loopback_listing_urls_are_rejected() -> None:
    for url in ("http://127.0.0.1/listing", "http://localhost/listing"):
        try:
            asyncio.run(_validate_public_url(url))
        except ValueError as exc:
            assert "공개 인터넷 주소" in str(exc)
        else:
            raise AssertionError("private listing URL must be rejected")

