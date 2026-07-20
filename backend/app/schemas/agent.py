from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.recommendation import (
    FitReason,
    RecommendationItem,
    RecommendationRequestSchema,
    RentalEstimateSchema,
)
from backend.app.services.cost_provider import FloorType, PropertyType


class AgentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)


class FounderContext(BaseModel):
    """Narrative founder context that must not be confused with scored engine inputs."""

    model_config = ConfigDict(extra="forbid")

    business_description: str | None = Field(default=None, max_length=500)
    target_customer: str | None = Field(default=None, max_length=300)
    operating_pattern: str | None = Field(default=None, max_length=300)
    location_flexibility: Literal["fixed", "flexible", "open"] | None = None
    risk_tolerance: Literal["low", "medium", "high"] | None = None
    budget_note: str | None = Field(default=None, max_length=300)
    priorities: list[str] = Field(default_factory=list, max_length=5)
    discovery_question_count: int = Field(0, ge=0, le=4)


class AgentAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=300)
    source_field: str = Field(min_length=1, max_length=80)
    status: Literal["inferred", "confirmed", "rejected"] = "inferred"


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
    strategy: Literal["balanced", "condition_fit", "growth", "stability"] = "balanced"
    total_startup_budget_krw: float | None = Field(default=None, gt=0)
    monthly_converted_rent_limit_krw: float | None = Field(default=None, gt=0)
    rentable_area_sqm: float | None = Field(default=None, gt=0, le=10_000)
    commercial_property_type: PropertyType | None = None
    floor: FloorType | None = None

    def has_preference(self) -> bool:
        values = self.model_dump(exclude={
            "industry_code", "top_n", "strategy", "total_startup_budget_krw",
            "monthly_converted_rent_limit_krw", "rentable_area_sqm",
            "commercial_property_type", "floor",
        }).values()
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
    context: FounderContext = Field(default_factory=FounderContext)
    assumptions: list[AgentAssumption] = Field(default_factory=list, max_length=10)
    missing_fields: list[str] = Field(default_factory=list, max_length=5)
    comparison_area_codes: list[str] = Field(default_factory=list, max_length=5)


class AgentTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["message", "select_scenario", "confirm_recommendation"] = "message"
    message: str = Field(min_length=1, max_length=2_000)
    history: list[AgentMessage] = Field(default_factory=list, max_length=20)
    draft: RecommendationDraft = Field(default_factory=RecommendationDraft)
    context: FounderContext = Field(default_factory=FounderContext)
    assumptions: list[AgentAssumption] = Field(default_factory=list, max_length=10)
    scenario_id: Literal["condition_fit", "growth", "stability"] | None = None
    selected_scenario_id: Literal["condition_fit", "growth", "stability"] | None = None
    analysis_revision: int = Field(0, ge=0)
    active_recommendation_request: RecommendationRequestSchema | None = None

    @model_validator(mode="after")
    def confirmation_requires_ready_draft(self) -> "AgentTurnRequest":
        if self.action == "confirm_recommendation":
            self.draft.to_request()
        if self.action == "select_scenario" and self.scenario_id is None:
            raise ValueError("선택할 scenario_id가 필요합니다.")
        return self


class StrategyScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["condition_fit", "growth", "stability"]
    strategy: Literal["condition_fit", "growth", "stability"]
    title: str
    description: str
    request: RecommendationRequestSchema
    candidate_count: int
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    diagnostics: dict[str, object] = Field(default_factory=dict)
    relaxed_fields: list[str] = Field(default_factory=list)


class TradeoffInsight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["candidate_scarcity", "preference_conflict", "strategy_disagreement"]
    message: str
    severity: Literal["info", "warning"]


class RelaxationOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    relaxed_fields: list[Literal["preferred_districts", "preferred_area_types"]]
    candidate_count_before: int
    candidate_count_after: int
    request: RecommendationRequestSchema


class DataGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["commercial_cost"]
    message: str


class MarketLookupRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    entity_code: str | None = None
    entity_name: str
    metric_value: float
    metric_display_value: str
    difference_from_mean: float
    difference_from_mean_display: str
    difference_from_median: float
    difference_from_median_display: str
    standard_deviation_distance: float
    district_name: str | None = None
    admin_dong_name: str | None = None
    area_count: int = Field(ge=1)
    observation_count: int = Field(ge=1)


class MarketLookupDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    population_count: int = Field(ge=1)
    mean: float
    mean_display: str
    median: float
    median_display: str
    standard_deviation: float = Field(ge=0)
    standard_deviation_display: str


class MarketLookupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    group_by: Literal["area", "industry", "district", "admin_dong"]
    metric: Literal[
        "sales", "closing_rate", "opening_rate", "growth_rate",
        "store_count", "store_density", "floating_population",
        "resident_population", "worker_population",
    ]
    metric_label: str
    metric_unit: Literal["krw", "ratio", "count", "count_per_sqkm", "people"]
    order: Literal["desc", "asc"]
    filters: dict[str, str] = Field(default_factory=dict)
    data_period: str
    distribution: MarketLookupDistribution
    rows: list[MarketLookupRow]
    geographic_basis: str
    disclosure: str


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
    recent_store_count: float | None = None
    same_industry_store_density: float | None = None
    recent_4q_average_sales: float | None = None
    recent_4q_growth_rate: float | None = None
    closing_rate: float | None = None
    data_reliability: float | None = None
    reliability_grade: str | None = None


class RecommendationReportMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_score: float | None = None
    condition_fit_score: float | None = None
    reliability_adjusted_evidence_score: float | None = None
    recent_4q_average_sales: float | None = None
    recent_4q_growth_rate: float | None = None
    recent_store_count: float | None = None
    same_industry_store_density: float | None = None
    closing_rate: float | None = None
    floating_population: float | None = None
    resident_population: float | None = None
    worker_population: float | None = None
    data_reliability: float | None = None
    estimated_converted_monthly_rent_krw: float | None = None
    unit_converted_rent_krw_sqm: float | None = None


class RecommendationReportArea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    area_code: str
    area_name: str
    district_name: str
    area_type: str
    reliability_grade: str
    base_final_score: float | None = None
    budget_fit_score: float | None = None
    rental_estimate: RentalEstimateSchema | None = None
    metrics: RecommendationReportMetrics
    benchmark_delta: RecommendationReportMetrics
    positive_reasons: list[FitReason] = Field(default_factory=list)
    negative_reasons: list[FitReason] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RecommendationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_count: int
    benchmark_label: str
    data_period: dict[str, str]
    competition_reference_period: str
    rental_estimate_basis: str
    rental_estimate_uses_default: bool
    benchmark: RecommendationReportMetrics
    areas: list[RecommendationReportArea]


class AgentTurnResponse(BaseModel):
    request_id: str
    artifact_version: str
    assistant_message: str
    phase: Literal["discovering", "exploring", "scenarios_ready", "ready_for_confirmation", "results"]
    draft: RecommendationDraft
    context: FounderContext = Field(default_factory=FounderContext)
    assumptions: list[AgentAssumption] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    confirmation_summary: str | None = None
    exploration_summary: dict[str, object] = Field(default_factory=dict)
    scenarios: list[StrategyScenario] = Field(default_factory=list)
    tradeoffs: list[TradeoffInsight] = Field(default_factory=list)
    relaxation_options: list[RelaxationOption] = Field(default_factory=list)
    data_gaps: list[DataGap] = Field(default_factory=list)
    selected_scenario_id: Literal["condition_fit", "growth", "stability"] | None = None
    analysis_revision: int = 0
    recommendations: list[RecommendationItem] = Field(default_factory=list)
    diagnostics: dict[str, object] = Field(default_factory=dict)
    comparison: list[AreaComparison] = Field(default_factory=list)
    recommendation_report: RecommendationReport | None = None
    market_lookup: MarketLookupResult | None = None
