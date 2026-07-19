import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.agent import (
    AgentDecision,
    AgentTurnRequest,
    RecommendationDraft,
)
from backend.app.services.agent_service import AgentExecution, LocationAgentService
from backend.app.services.recommender_service import RecommenderService


ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts/current"


class ReadyRunner:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def run(self, payload, recommender, metadata) -> AgentExecution:
        self.actions.append(payload.action)
        draft = RecommendationDraft(
            industry_code="CS100001",
            preferred_districts=["강남구"],
            top_n=3,
        )
        if payload.action == "confirm_recommendation":
            items, diagnostics = recommender.recommend(draft.to_request())
            return AgentExecution(
                AgentDecision(
                    assistant_message="확인한 조건으로 추천했습니다.",
                    draft=draft,
                ),
                items,
                diagnostics,
            )
        return AgentExecution(
            AgentDecision(
                assistant_message="해석한 조건이 맞는지 확인해주세요.",
                draft=draft,
            )
        )


class ComparisonRunner:
    async def run(self, payload, recommender, metadata) -> AgentExecution:
        comparison = recommender.compare(
            [recommender.recommend(payload.active_recommendation_request)[0][0]["area_code"]],
            payload.active_recommendation_request.industry_code,
        )
        return AgentExecution(
            AgentDecision(
                assistant_message="현재 추천 후보를 비교했습니다.",
                draft=RecommendationDraft(**payload.active_recommendation_request.model_dump()),
                comparison_area_codes=[comparison[0]["area_code"]],
            ),
            comparison=comparison,
        )


def test_agent_moves_to_confirmation_without_running_recommendation() -> None:
    runner = ReadyRunner()
    service = LocationAgentService(
        RecommenderService(ARTIFACT_DIR), runner, timeout_seconds=1,
    )
    result = asyncio.run(service.turn(AgentTurnRequest(message="강남에서 한식집을 열고 싶어요")))

    assert result["phase"] == "ready_for_confirmation"
    assert result["recommendations"] == []
    assert runner.actions == ["message"]
    assert "강남구" in result["confirmation_summary"]


def test_confirm_action_returns_deterministic_recommendations() -> None:
    runner = ReadyRunner()
    service = LocationAgentService(
        RecommenderService(ARTIFACT_DIR), runner, timeout_seconds=1,
    )
    draft = RecommendationDraft(
        industry_code="CS100001", preferred_districts=["강남구"], top_n=3,
    )
    result = asyncio.run(service.turn(AgentTurnRequest(
        action="confirm_recommendation",
        message="이 조건으로 분석해주세요.",
        draft=draft,
    )))

    assert result["phase"] == "results"
    assert len(result["recommendations"]) == 3
    assert runner.actions == ["confirm_recommendation"]


def test_agent_api_contract_with_injected_runner() -> None:
    with TestClient(app) as client:
        runner = ReadyRunner()
        app.state.location_agent = LocationAgentService(
            app.state.recommender, runner, timeout_seconds=1,
        )
        response = client.post("/api/v1/agent/turns", json={
            "message": "강남에서 한식집을 열고 싶어요",
            "draft": {},
        })

        assert response.status_code == 200
        body = response.json()
        assert body["phase"] == "ready_for_confirmation"
        assert body["draft"]["industry_code"] == "CS100001"
        assert body["request_id"] == response.headers["x-request-id"]


def test_confirmation_requires_ready_draft() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/agent/turns", json={
            "action": "confirm_recommendation",
            "message": "분석해주세요",
            "draft": {"industry_code": "CS100001"},
        })
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "REQUEST_SCHEMA_VALIDATION_FAILED"


def test_comparison_follow_up_keeps_results_phase() -> None:
    recommender = RecommenderService(ARTIFACT_DIR)
    active_request = RecommendationDraft(
        industry_code="CS100001", target_age_groups=["20"], top_n=3,
    ).to_request()
    service = LocationAgentService(recommender, ComparisonRunner(), timeout_seconds=1)
    result = asyncio.run(service.turn(AgentTurnRequest(
        message="1위 후보를 설명해주세요",
        draft=RecommendationDraft(**active_request.model_dump()),
        active_recommendation_request=active_request,
    )))
    assert result["phase"] == "results"
    assert len(result["comparison"]) == 1


def test_compare_is_limited_to_current_recommendations() -> None:
    recommender = RecommenderService(ARTIFACT_DIR)
    request = RecommendationDraft(
        industry_code="CS100001", target_age_groups=["20"], top_n=3,
    ).to_request()
    items, _ = recommender.recommend(request)
    allowed = {item["area_code"] for item in items}
    comparison = recommender.compare(
        [items[0]["area_code"], items[1]["area_code"]],
        request.industry_code,
        allowed_area_codes=allowed,
    )
    assert [item["area_code"] for item in comparison] == [
        items[0]["area_code"], items[1]["area_code"],
    ]
    assert comparison[0]["apartment_average_market_price"] is not None

    with pytest.raises(ValueError, match="현재 추천 결과"):
        recommender.compare(["not-a-result"], request.industry_code, allowed_area_codes=allowed)
