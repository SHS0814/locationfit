from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.services.cost_provider import FloorType, PropertyType


class RecommendationRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry_code: str = Field(min_length=1)
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

    @model_validator(mode="after")
    def validate_rental_conditions(self) -> "RecommendationRequestSchema":
        fields = (self.rentable_area_sqm, self.commercial_property_type, self.floor)
        if any(value is not None for value in fields) and not all(value is not None for value in fields):
            raise ValueError("임대료 추정에는 임대면적, 상가 유형, 층을 모두 입력해야 합니다.")
        if self.monthly_converted_rent_limit_krw is not None and not all(
            value is not None for value in fields
        ):
            raise ValueError("월 환산임대료 한도를 적용하려면 임대면적, 상가 유형, 층이 필요합니다.")
        return self


class FitReason(BaseModel):
    factor: str
    feature: str
    fit_score: float
    weight: float


class AreaBoundary(BaseModel):
    type: Literal["Polygon", "MultiPolygon"]
    coordinates: list[Any]


class RecommendationItem(BaseModel):
    rank: int
    area_code: str
    area_name: str
    district_name: str
    admin_dong_name: str | None = None
    area_type: str
    industry_code: str
    industry_name: str
    latitude: float
    longitude: float
    area_size_sqm: float
    boundary: AreaBoundary
    final_score: float
    base_final_score: float | None = None
    budget_fit_score: float | None = None
    budget_adjusted: bool = False
    condition_fit_score: float
    raw_evidence_score: float | None
    reliability_adjusted_evidence_score: float | None
    data_reliability: float
    reliability_grade: str
    positive_reasons: list[FitReason]
    negative_reasons: list[FitReason]
    evidence_summary: dict[str, Any]
    warnings: list[str]
    rental_estimate: "RentalEstimateSchema | None" = None


class RentalEstimateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    property_type: PropertyType
    floor: FloorType
    rentable_area_sqm: float
    unit_converted_rent_krw_sqm: float
    estimated_converted_monthly_rent_krw: float
    annual_conversion_rate: float
    reference_period: str
    survey_area_name: str
    survey_area_distance_km: float
    mapping_method: Literal["nearest_reb_survey_market"]
    source: str
    disclosure: str


class RecommendationResponse(BaseModel):
    request_id: str
    artifact_version: str
    recommendations: list[RecommendationItem]
    diagnostics: dict[str, Any]


class MetadataOption(BaseModel):
    code: str
    name: str


class CommercialPropertyTypeOption(MetadataOption):
    floors: list[MetadataOption]


class MetadataResponse(BaseModel):
    artifact_version: str
    data_period: dict[str, str]
    industries: list[MetadataOption]
    districts: list[str]
    area_types: list[MetadataOption]
    age_groups: list[MetadataOption]
    time_bands: list[MetadataOption]
    commercial_property_types: list[CommercialPropertyTypeOption]
