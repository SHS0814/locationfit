from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import shape

from backend.app.schemas.agent import FounderContext
from backend.app.schemas.recommendation import RecommendationRequestSchema
from backend.app.schemas.research import WebResearchRequest
from backend.app.services.recommender_service import RecommenderService
from backend.app.services.store_service import CommercialStoreService, StoreFetchResult
from backend.app.services.web_research_service import WebResearchService, _collect_sources


ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts/current"


class Provider:
    def __init__(self, row):
        self.row = row

    async def fetch(self, geometry):
        return StoreFetchResult([self.row], "202607")


class Runner:
    def __init__(self):
        self.contexts = []

    async def run(self, research_context):
        self.contexts.append(research_context)
        return "출처에서 확인된 최신 정보입니다.", [{"title": "공식 출처", "url": "https://example.com/source"}]


def setup_services():
    recommender = RecommenderService(ARTIFACT_DIR)
    request = RecommendationRequestSchema(industry_code="CS100001", top_n=3)
    recommendations, _ = recommender.recommend(request)
    selected = recommendations[0]
    point = shape(recommender.boundaries[selected["area_code"]]).representative_point()
    row = {
        "bizesId": "STORE-1", "bizesNm": "테스트 식당", "indsSclsNm": "한식 음식점업",
        "rdnmAdr": "서울특별시 테스트로 1", "lon": point.x, "lat": point.y,
    }
    stores = CommercialStoreService(recommender, Provider(row))
    runner = Runner()
    research = WebResearchService(recommender, stores, runner, timeout_seconds=1)
    return request, selected, runner, research


def test_area_and_store_research_receive_confirmed_context() -> None:
    request, selected, runner, service = setup_services()
    area_result = asyncio.run(service.research(WebResearchRequest(
        scope="area", area_code=selected["area_code"], industry_code="CS100001",
        active_recommendation_request=request,
        context=FounderContext(target_customer="직장인"),
    )))
    store_result = asyncio.run(service.research(WebResearchRequest(
        scope="store", area_code=selected["area_code"], industry_code="CS100001",
        store_id="STORE-1", active_recommendation_request=request,
    )))
    assert area_result["sources"][0]["url"] == "https://example.com/source"
    assert store_result["store_id"] == "STORE-1"
    assert runner.contexts[0]["area"]["area_name"] == selected["area_name"]
    assert runner.contexts[1]["selected_store"]["road_address"]
    assert any("동명이업소" in warning for warning in store_result["warnings"])


def test_research_rejects_area_outside_current_recommendations() -> None:
    request, _, _, service = setup_services()
    try:
        asyncio.run(service.research(WebResearchRequest(
            scope="area", area_code="not-recommended", industry_code="CS100001",
            active_recommendation_request=request,
        )))
    except ValueError as exc:
        assert "현재 추천 결과" in str(exc)
    else:
        raise AssertionError("unrecommended area must be rejected")


def test_source_extraction_keeps_only_http_urls_and_deduplicates() -> None:
    @dataclass
    class Response:
        output: list

    sources = _collect_sources([Response(output=[{
        "action": {"sources": [
            {"title": "A", "url": "https://example.com/a"},
            {"title": "duplicate", "url": "https://example.com/a"},
            {"title": "unsafe", "url": "javascript:alert(1)"},
        ]},
    }])])
    assert sources == [{"title": "A", "url": "https://example.com/a"}]
