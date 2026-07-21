from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas.agent import FounderContext
from backend.app.schemas.recommendation import RecommendationRequestSchema


class WebResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["area", "store"]
    area_code: str = Field(min_length=1)
    industry_code: str = Field(min_length=1)
    store_id: str | None = None
    active_recommendation_request: RecommendationRequestSchema
    context: FounderContext = Field(default_factory=FounderContext)

    @model_validator(mode="after")
    def validate_scope(self) -> "WebResearchRequest":
        if self.scope == "store" and not self.store_id:
            raise ValueError("업소 웹 검색에는 store_id가 필요합니다.")
        if self.active_recommendation_request.industry_code != self.industry_code:
            raise ValueError("현재 추천 업종과 웹 검색 업종이 일치하지 않습니다.")
        return self


class WebResearchSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str


class WebResearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    scope: Literal["area", "store"]
    area_code: str
    store_id: str | None = None
    subject: str
    summary: str
    sources: list[WebResearchSource]
    searched_at: str
    warnings: list[str] = Field(default_factory=list)

