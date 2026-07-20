import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.agent import (
    AgentDecision,
    AgentTurnRequest,
    FounderContext,
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
                assistant_message="데이터를 탐색하겠습니다.",
                draft=draft,
                context=FounderContext(
                    target_customer="직장인 점심 고객",
                    location_flexibility="fixed",
                ),
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


class IncompleteRunner:
    async def run(self, payload, recommender, metadata) -> AgentExecution:
        return AgentExecution(AgentDecision(
            assistant_message="고객과 시간과 지역을 모두 알려주세요? 두 번째 질문도요?",
            draft=RecommendationDraft(industry_code="CS100001"),
        ))


class MarketLookupRunner:
    async def run(self, payload, recommender, metadata) -> AgentExecution:
        lookup = recommender.lookup_market_rankings(
            group_by="industry",
            metric="closing_rate",
            top_n=5,
            district_name="강남구",
            admin_dong_name="역삼1동",
        )
        return AgentExecution(
            AgentDecision(
                assistant_message="역삼1동의 폐업률 상위 업종을 조회했습니다. 행정동 기준입니다.",
                draft=RecommendationDraft(industry_code="not-a-real-code"),
            ),
            market_lookup=lookup,
        )


def test_agent_explores_three_scenarios_without_final_recommendation() -> None:
    runner = ReadyRunner()
    service = LocationAgentService(
        RecommenderService(ARTIFACT_DIR), runner, timeout_seconds=1,
    )
    result = asyncio.run(service.turn(AgentTurnRequest(message="강남에서 한식집을 열고 싶어요")))

    assert result["phase"] == "scenarios_ready"
    assert result["recommendations"] == []
    assert runner.actions == ["message"]
    assert [item["id"] for item in result["scenarios"]] == [
        "condition_fit", "growth", "stability",
    ]
    assert result["analysis_revision"] == 1


def test_discovery_asks_one_question_and_applies_defaults_after_four_turns() -> None:
    service = LocationAgentService(
        RecommenderService(ARTIFACT_DIR), IncompleteRunner(), timeout_seconds=1,
    )
    payload = AgentTurnRequest(message="한식집을 열고 싶어요")
    for turn in range(4):
        result = asyncio.run(service.turn(payload))
        if turn < 3:
            assert result["phase"] == "discovering"
            assert result["assistant_message"].count("?") <= 1
        payload = AgentTurnRequest(
            message="아직 잘 모르겠어요",
            draft=result["draft"],
            context=result["context"],
            assumptions=result["assumptions"],
            analysis_revision=result["analysis_revision"],
        )

    assert result["phase"] == "scenarios_ready"
    assert result["context"].location_flexibility == "open"
    assert result["context"].risk_tolerance == "medium"
    assert result["draft"].min_data_reliability == 0.5


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
    assert result["recommendation_report"] is not None
    assert len(result["recommendation_report"]["areas"]) == 3
    assert result["recommendations"][0]["area_name"] in result["assistant_message"]
    assert "중앙값" in result["assistant_message"]
    assert "동종업종 점포" in result["assistant_message"]
    assert "점포 밀도" in result["assistant_message"]
    assert "경쟁강도" not in result["assistant_message"]
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
        assert body["phase"] == "scenarios_ready"
        assert body["draft"]["industry_code"] == "CS100001"
        assert len(body["scenarios"]) == 3
        assert body["request_id"] == response.headers["x-request-id"]

        confirm_response = client.post("/api/v1/agent/turns", json={
            "action": "confirm_recommendation",
            "message": "이 조건으로 분석해주세요.",
            "draft": {
                "industry_code": "CS100001",
                "preferred_districts": ["강남구"],
                "top_n": 3,
            },
        })
        assert confirm_response.status_code == 200
        confirm_body = confirm_response.json()
        assert len(confirm_body["recommendation_report"]["areas"]) == 3
        assert confirm_body["recommendation_report"]["candidate_count"] > 0
        assert confirm_body["recommendation_report"]["competition_reference_period"] == "2025Q4"
        assert confirm_body["recommendation_report"]["areas"][0]["metrics"]["recent_store_count"] is not None
        assert confirm_body["recommendation_report"]["areas"][0]["metrics"]["same_industry_store_density"] is not None


def test_select_scenario_requires_confirmation_before_final_result() -> None:
    service = LocationAgentService(
        RecommenderService(ARTIFACT_DIR), ReadyRunner(), timeout_seconds=1,
    )
    draft = RecommendationDraft(
        industry_code="CS100001", preferred_districts=["강남구"], top_n=3,
    )
    result = asyncio.run(service.turn(AgentTurnRequest(
        action="select_scenario",
        message="안정성 우선형을 선택합니다.",
        draft=draft,
        scenario_id="stability",
        selected_scenario_id="stability",
        analysis_revision=1,
    )))

    assert result["phase"] == "ready_for_confirmation"
    assert result["draft"].strategy == "stability"
    assert result["recommendations"] == []
    assert "안정성 우선형" in result["confirmation_summary"]


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
    assert comparison[0]["recent_store_count"] is not None
    assert comparison[0]["same_industry_store_density"] is not None

    with pytest.raises(ValueError, match="현재 추천 결과"):
        recommender.compare(["not-a-result"], request.industry_code, allowed_area_codes=allowed)


def test_market_lookup_bypasses_recommendation_discovery_and_preserves_state() -> None:
    service = LocationAgentService(
        RecommenderService(ARTIFACT_DIR), MarketLookupRunner(), timeout_seconds=1,
    )
    original_draft = RecommendationDraft(industry_code="CS100001", preferred_districts=["강남구"])
    result = asyncio.run(service.turn(AgentTurnRequest(
        message="강남구 역삼1동에서 폐업률 높은 업종 5개 알려줘",
        draft=original_draft,
    )))

    assert result["phase"] == "discovering"
    assert result["draft"] == original_draft
    assert result["market_lookup"]["metric"] == "closing_rate"
    assert len(result["market_lookup"]["rows"]) == 5
    assert result["recommendations"] == []


def test_market_lookup_api_contract() -> None:
    with TestClient(app) as client:
        app.state.location_agent = LocationAgentService(
            app.state.recommender, MarketLookupRunner(), timeout_seconds=1,
        )
        response = client.post("/api/v1/agent/turns", json={
            "message": "강남구 역삼1동에서 폐업률 높은 업종 5개 알려줘",
            "draft": {},
        })

        assert response.status_code == 200
        lookup = response.json()["market_lookup"]
        assert lookup["group_by"] == "industry"
        assert lookup["metric"] == "closing_rate"
        assert lookup["distribution"]["population_count"] >= len(lookup["rows"])
        assert lookup["distribution"]["mean_display"].endswith("%")
        assert lookup["rows"][0]["metric_display_value"].endswith("%")
