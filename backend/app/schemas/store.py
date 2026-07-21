from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StorePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: str
    name: str
    branch_name: str | None = None
    industry_large_code: str | None = None
    industry_large_name: str | None = None
    industry_middle_code: str | None = None
    industry_middle_name: str | None = None
    industry_small_code: str | None = None
    industry_small_name: str | None = None
    ksic_code: str | None = None
    ksic_name: str | None = None
    road_address: str | None = None
    lot_address: str | None = None
    building_name: str | None = None
    building_management_number: str | None = None
    floor: str | None = None
    unit: str | None = None
    longitude: float
    latitude: float
    relation: Literal["competitor", "complementary", "daily_life", "other"]


class StoreRelationCount(BaseModel):
    relation: Literal["competitor", "complementary", "daily_life", "other"]
    count: int = Field(ge=0)


class StoreCategoryCount(BaseModel):
    code: str | None = None
    name: str
    count: int = Field(ge=1)


class StoreAnalysisSummary(BaseModel):
    total_count: int = Field(ge=0)
    total_density_per_sqkm: float = Field(ge=0)
    competitor_count: int = Field(ge=0)
    competitor_density_per_sqkm: float = Field(ge=0)
    relation_counts: list[StoreRelationCount]
    top_categories: list[StoreCategoryCount]


class AreaStoresResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    area_code: str
    area_name: str
    industry_code: str
    industry_name: str
    reference_month: str | None = None
    fetched_at: str
    cache_status: Literal["fresh", "refreshed", "stale"]
    source: str
    disclosure: str
    warnings: list[str] = Field(default_factory=list)
    summary: StoreAnalysisSummary
    stores: list[StorePoint]

