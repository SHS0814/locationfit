from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class FitReason(BaseModel):
    factor: str
    feature: str
    fit_score: float
    weight: float


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
    final_score: float
    condition_fit_score: float
    raw_evidence_score: float | None
    reliability_adjusted_evidence_score: float | None
    data_reliability: float
    reliability_grade: str
    positive_reasons: list[FitReason]
    negative_reasons: list[FitReason]
    evidence_summary: dict[str, Any]
    warnings: list[str]


class RecommendationResponse(BaseModel):
    request_id: str
    artifact_version: str
    recommendations: list[RecommendationItem]
    diagnostics: dict[str, Any]


class MetadataOption(BaseModel):
    code: str
    name: str


class MetadataResponse(BaseModel):
    artifact_version: str
    data_period: dict[str, str]
    industries: list[MetadataOption]
    districts: list[str]
    area_types: list[MetadataOption]
    age_groups: list[MetadataOption]
    time_bands: list[MetadataOption]
