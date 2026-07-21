from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.recommendation import RentalEstimateSchema
from backend.app.services.cost_provider import FloorType


class LeasePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_code: str = Field(min_length=1)
    floor: FloorType
    rentable_area_sqm: float = Field(gt=0, le=10_000)
    deposit_krw: float | None = Field(default=None, ge=0)
    total_startup_budget_krw: float | None = Field(default=None, gt=0)


class LeasePlanSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimated_converted_monthly_rent_krw: float
    deposit_krw: float | None
    cash_monthly_rent_krw: float | None
    annual_cash_rent_krw: float | None
    first_year_cash_outlay_krw: float | None
    refundable_deposit_krw: float | None
    remaining_startup_budget_krw: float | None
    deposit_share_of_budget: float | None
    annual_conversion_rate: float
    disclosure: str


class LeasePlanResponse(BaseModel):
    request_id: str
    rental_estimate: RentalEstimateSchema
    lease_plan: LeasePlanSchema
