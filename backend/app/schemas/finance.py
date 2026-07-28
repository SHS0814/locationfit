from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


Money = int


class ConfirmedLeaseCandidate(BaseModel):
    source_url: HttpUrl | None = None
    listing_title: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=300)
    deposit_krw: Money = Field(ge=0)
    monthly_rent_krw: Money = Field(ge=0)
    management_fee_krw: Money = Field(ge=0)
    key_money_krw: Money = Field(ge=0)
    rentable_area_sqm: float | None = Field(default=None, gt=0, le=100_000)
    floor: str | None = Field(default=None, max_length=80)


class StartupAdditionalCosts(BaseModel):
    interior_krw: Money = Field(default=0, ge=0)
    equipment_krw: Money = Field(default=0, ge=0)
    initial_inventory_krw: Money = Field(default=0, ge=0)
    working_capital_krw: Money = Field(default=0, ge=0)
    other_krw: Money = Field(default=0, ge=0)


class FounderEligibility(BaseModel):
    own_capital_krw: Money = Field(ge=0)
    business_status: Literal["pre_startup", "operating"]
    business_age_months: int | None = Field(default=None, ge=0, le=1_200)
    is_small_business: bool | None = None
    vulnerability: Literal[
        "low_credit", "basic_livelihood", "near_poverty", "earned_income_tax_credit",
        "none", "unknown",
    ] = "unknown"
    has_policy_excluded_industry: bool | None = None

    @model_validator(mode="after")
    def validate_business_age(self) -> "FounderEligibility":
        if self.business_status == "operating" and self.business_age_months is None:
            raise ValueError("영업 중인 경우 업력(개월)을 입력해주세요.")
        return self


class FinancePlanRequest(BaseModel):
    candidate: ConfirmedLeaseCandidate
    additional_costs: StartupAdditionalCosts = Field(default_factory=StartupAdditionalCosts)
    eligibility: FounderEligibility


class FundingSummary(BaseModel):
    refundable_deposit_krw: Money
    one_time_nonrefundable_krw: Money
    annual_occupancy_cost_krw: Money
    additional_startup_cost_krw: Money
    total_first_year_cash_need_krw: Money
    own_capital_krw: Money
    funding_gap_krw: Money
    own_capital_ratio: float


class PolicyCandidate(BaseModel):
    program_id: str
    name: str
    provider: str
    product_type: Literal["bank_loan", "policy_fund", "support_program", "guarantee"]
    catalog_status: Literal["active", "upcoming", "unknown"]
    summary: str | None
    status: Literal["basic_fit", "needs_review", "not_eligible"]
    reasons: list[str]
    checks_required: list[str]
    benefits: list["CatalogBenefit"]
    application_url: HttpUrl | None
    application_end_date: str | None
    source_title: str
    source_url: HttpUrl
    source_checked_at: str


class CatalogBenefit(BaseModel):
    benefit_type: Literal["loan", "guarantee", "interest_subsidy", "grant", "other"]
    amount_min_krw: Money | None
    amount_max_krw: Money | None
    interest_rate_min_pct: float | None
    interest_rate_max_pct: float | None
    guarantee_rate_pct: float | None
    interest_subsidy_rate_pct: float | None
    guarantee_fee_rate_pct: float | None
    term_min_months: int | None
    term_max_months: int | None
    grace_period_months: int | None
    original_text: str | None


class FinancePlanResponse(BaseModel):
    request_id: str
    funding: FundingSummary
    policy_candidates: list[PolicyCandidate]
    disclosure: str
