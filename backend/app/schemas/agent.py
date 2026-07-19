from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.recommendation import RecommendationItem, RecommendationRequestSchema


class AgentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)


class RecommendationDraft(BaseModel):
    """Editable recommendation conditions while the conversation is in progress."""

    model_config = ConfigDict(extra="forbid")

    industry_code: str | None = None
    preferred_area_types: list[str] = Field(default_factory=list)
    target_gender: Literal["male", "female"] | None = None
    target_age_groups: list[Literal["10", "20", "30", "40", "50", "60_plus"]] = Field(default_factory=list)
    preferred_time_bands: list[Literal["00_06", "06_11", "11_14", "14_17", "17_21", "21_24"]] = Field(default_factory=list)
    weekend_importance: float = Field(0, ge=0, le=1)
    floating_population_importance: float = Field(0, ge=0, le=1)
    resident_population_importance: float = Field(0, ge=0, le=1)
    worker_population_importance: float = Field(0, ge=0, le=1)
    apartment_importance: float = Field(0, ge=0, le=1)
    transport_facility_importance: float = Field(0, ge=0, le=1)
    education_facility_importance: float = Field(0, ge=0, le=1)
    medical_facility_importance: float = Field(0, ge=0, le=1)
    shopping_facility_importance: float = Field(0, ge=0, le=1)
    culture_facility_importance: float = Field(0, ge=0, le=1)
    store_density_preference: Literal["high", "low"] | None = None
    franchise_preference: Literal["high", "low"] | None = None
    preferred_districts: list[str] = Field(default_factory=list)
    excluded_districts: list[str] = Field(default_factory=list)
    min_data_reliability: float = Field(0, ge=0, le=1)
    top_n: int = Field(10, ge=1, le=50)

    def has_preference(self) -> bool:
        values = self.model_dump(exclude={"industry_code", "top_n"}).values()
        return any(bool(value) for value in values)

    def to_request(self) -> RecommendationRequestSchema:
        if not self.industry_code:
            raise ValueError("업종을 먼저 알려주세요.")
        if not self.has_preference():
            raise ValueError("업종 외에 원하는 조건을 하나 이상 알려주세요.")
        return RecommendationRequestSchema(**self.model_dump())


class AgentDecision(BaseModel):
    """Strict structured output produced by the LLM."""

    model_config = ConfigDict(extra="forbid")

    assistant_message: str = Field(min_length=1, max_length=2_000)
    draft: RecommendationDraft
    missing_fields: list[str] = Field(default_factory=list, max_length=5)
    comparison_area_codes: list[str] = Field(default_factory=list, max_length=5)


class AgentTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["message", "confirm_recommendation"] = "message"
    message: str = Field(min_length=1, max_length=2_000)
    history: list[AgentMessage] = Field(default_factory=list, max_length=20)
    draft: RecommendationDraft = Field(default_factory=RecommendationDraft)
    active_recommendation_request: RecommendationRequestSchema | None = None

    @model_validator(mode="after")
    def confirmation_requires_ready_draft(self) -> "AgentTurnRequest":
        if self.action == "confirm_recommendation":
            self.draft.to_request()
        return self


class AreaComparison(BaseModel):
    area_code: str
    area_name: str
    district_name: str
    area_type: str
    floating_population: float | None = None
    resident_population: float | None = None
    worker_population: float | None = None
    transport_facility_count: float | None = None
    education_facility_count: float | None = None
    medical_facility_count: float | None = None
    shopping_facility_count: float | None = None
    culture_facility_count: float | None = None
    apartment_average_market_price: float | None = None
    competition_intensity: float | None = None
    recent_4q_average_sales: float | None = None
    recent_4q_growth_rate: float | None = None
    closing_rate: float | None = None
    data_reliability: float | None = None
    reliability_grade: str | None = None


class AgentTurnResponse(BaseModel):
    request_id: str
    artifact_version: str
    assistant_message: str
    phase: Literal["gathering", "ready_for_confirmation", "results"]
    draft: RecommendationDraft
    missing_fields: list[str] = Field(default_factory=list)
    confirmation_summary: str | None = None
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    diagnostics: dict[str, object] = Field(default_factory=dict)
    comparison: list[AreaComparison] = Field(default_factory=list)
