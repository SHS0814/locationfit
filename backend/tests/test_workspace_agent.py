import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_workspace_agent
from backend.app.financial_catalog.loader import load_curated_catalog
from backend.app.main import app
from backend.app.schemas.agent import WorkspaceAgentRequest
from backend.app.services.finance_service import FinancePlanService
from backend.app.services.workspace_agent_service import (
    WorkspaceAgentExecution,
    OpenAIWorkspaceAgentRunner,
    WorkspaceAgentDecision,
    WorkspaceAgentService,
    WorkspaceToolRuntime,
)


CATALOG = load_curated_catalog(
    Path(__file__).resolve().parents[2] / "config/financial_catalog"
)


class StaticCatalogProvider:
    def load(self):
        return CATALOG


class FakeStoreService:
    class FakeRecommender:
        @staticmethod
        def recommend(payload):
            del payload
            return [{"area_code": "A-1"}], {}

    recommender = FakeRecommender()

    async def analyse(self, area_code, industry_code):
        return {
            "area_code": area_code,
            "area_name": "테스트상권",
            "industry_code": industry_code,
            "industry_name": "한식음식점",
            "reference_month": "202607",
            "fetched_at": "2026-07-29T00:00:00Z",
            "cache_status": "fresh",
            "source": "테스트 상가업소",
            "disclosure": "임대 가능 여부는 알 수 없습니다.",
            "warnings": [],
            "summary": {
                "total_count": 3,
                "competitor_count": 1,
                "competitor_density_per_sqkm": 2.5,
            },
            "stores": [{
                "store_id": "STORE-1", "name": "테스트식당", "relation": "competitor",
                "industry_small_name": "한식", "road_address": "서울 테스트로 1",
            }],
        }


class FakeWebResearchService:
    def __init__(self):
        self.calls = 0

    async def research(self, payload):
        self.calls += 1
        return {
            "scope": payload.scope, "area_code": payload.area_code,
            "store_id": payload.store_id, "subject": "테스트상권",
            "summary": "출처가 확인된 최근 정보입니다.",
            "sources": [{"title": "공식 출처", "url": "https://example.com"}],
            "searched_at": "2026-07-29T00:00:00Z", "warnings": [],
        }


class RecordingRunner:
    def __init__(self) -> None:
        self.workspace = None
        self.conversation = None
        self.runtime = None

    async def run(self, workspace, conversation, runtime):
        self.workspace = workspace
        self.conversation = conversation
        self.runtime = runtime
        return WorkspaceAgentExecution("현재 상권의 점포 집계만 기준으로 설명했습니다.")


def store_request(message: str = "경쟁점이 많아?") -> WorkspaceAgentRequest:
    return WorkspaceAgentRequest(
        workspace="stores",
        message=message,
        history=[{"role": "assistant", "content": "점포분석만 답합니다."}],
        state={
            "kind": "stores", "area_code": "A-1", "industry_code": "CS100001",
            "selected_store_id": "STORE-1",
            "active_recommendation_request": {"industry_code": "CS100001"},
            "founder_context": {},
        },
    )


def finance_request(message: str = "현재 자금계획을 계산해줘") -> WorkspaceAgentRequest:
    return WorkspaceAgentRequest(
        workspace="finance",
        message=message,
        state={
            "kind": "finance", "area_code": "A-1", "selected_candidate_id": "LEASE-1",
            "candidates": [{
                "id": "LEASE-1", "area_code": "A-1",
                "listing_title": "테스트 매물", "address": "서울 테스트로 2",
                "deposit_krw": 20_000_000, "monthly_rent_krw": 1_000_000,
                "management_fee_krw": 100_000, "key_money_krw": 0,
                "additional_costs": {"interior_krw": 10_000_000},
                "eligibility": {
                    "own_capital_krw": 25_000_000, "business_status": "pre_startup",
                    "is_small_business": True, "vulnerability": "unknown",
                },
            }],
        },
    )


def runtime(payload: WorkspaceAgentRequest, web=None) -> WorkspaceToolRuntime:
    return WorkspaceToolRuntime(
        payload,
        store_service=FakeStoreService(),
        web_research_service=web or FakeWebResearchService(),
        finance_service=FinancePlanService(),
        catalog_provider=StaticCatalogProvider(),
    )


def test_workspace_agent_keeps_page_scope_and_typed_state() -> None:
    runner = RecordingRunner()
    service = WorkspaceAgentService(
        runner,
        store_service=FakeStoreService(),
        web_research_service=FakeWebResearchService(),
        finance_service=FinancePlanService(),
        catalog_provider=StaticCatalogProvider(),
        timeout_seconds=1,
    )
    result = asyncio.run(service.turn(store_request()))

    assert result.assistant_message == "현재 상권의 점포 집계만 기준으로 설명했습니다."
    assert runner.workspace == "stores"
    assert runner.conversation["state"]["area_code"] == "A-1"
    assert runner.conversation["history"] == [
        {"role": "assistant", "content": "점포분석만 답합니다."},
    ]


def test_workspace_agent_api_returns_structured_tool_outputs() -> None:
    class EvidenceRunner:
        async def run(self, workspace, conversation, tool_runtime):
            del workspace, conversation
            await tool_runtime.analyse_current_area_stores(None, None, 10)
            return WorkspaceAgentExecution("도구로 확인했습니다.", list(tool_runtime.outputs))

    service = WorkspaceAgentService(
        EvidenceRunner(),
        store_service=FakeStoreService(),
        web_research_service=FakeWebResearchService(),
        finance_service=FinancePlanService(),
        catalog_provider=StaticCatalogProvider(),
        timeout_seconds=1,
    )
    app.dependency_overrides[get_workspace_agent] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/agent/workspace-turns",
                json=store_request().model_dump(mode="json"),
            )
        assert response.status_code == 200
        assert response.json()["tool_outputs"][0]["kind"] == "store_summary"
        assert response.json()["tool_outputs"][0]["payload"]["summary"]["competitor_count"] == 1
    finally:
        app.dependency_overrides.pop(get_workspace_agent, None)


def test_workspace_agent_request_rejects_mismatched_workspace() -> None:
    payload = store_request().model_dump(mode="json")
    payload["workspace"] = "finance"
    try:
        WorkspaceAgentRequest(**payload)
    except ValueError as exc:
        assert "workspace" in str(exc)
    else:
        raise AssertionError("mismatched workspace must be rejected")


def test_openai_runner_builds_workspace_specific_function_tools(monkeypatch) -> None:
    from agents import Runner

    async def fake_run(agent, run_input, max_turns):
        del run_input, max_turns
        assert len(agent.tools) >= 3
        return SimpleNamespace(final_output=WorkspaceAgentDecision(
            assistant_message="도구 사용 방법을 안내했습니다.", answer_basis="general",
        ))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(Runner, "run", fake_run)
    runner = OpenAIWorkspaceAgentRunner(model="test-model")

    store_result = asyncio.run(runner.run("stores", {}, runtime(store_request())))
    finance_result = asyncio.run(runner.run("finance", {}, runtime(finance_request())))

    assert store_result.assistant_message
    assert finance_result.assistant_message


def test_store_tools_are_bound_to_current_area_and_return_bounded_evidence() -> None:
    tool_runtime = runtime(store_request())
    result = json.loads(asyncio.run(
        tool_runtime.analyse_current_area_stores("competitor", None, 50)
    ))

    assert result["status"] == "succeeded"
    assert result["payload"]["area_code"] == "A-1"
    assert result["payload"]["matched_count"] == 1
    assert len(result["payload"]["stores"]) <= 10


def test_store_tool_rejects_area_outside_active_recommendations() -> None:
    payload = store_request()
    payload.state.area_code = "A-2"
    try:
        asyncio.run(runtime(payload).analyse_current_area_stores(None, None, 10))
    except ValueError as exc:
        assert "추천 결과" in str(exc)
    else:
        raise AssertionError("area outside the active recommendation must be rejected")


def test_store_web_research_requires_explicit_user_request() -> None:
    web = FakeWebResearchService()
    blocked = runtime(store_request("경쟁점이 많아?"), web)
    blocked_result = json.loads(asyncio.run(
        blocked.search_current_area_or_store("area", None)
    ))
    allowed = runtime(store_request("최근 외부 이슈를 검색해줘"), web)
    allowed_result = json.loads(asyncio.run(
        allowed.search_current_area_or_store("area", None)
    ))

    assert blocked_result["status"] == "failed"
    assert allowed_result["status"] == "succeeded"
    assert web.calls == 1


def test_finance_tool_matches_service_and_what_if_does_not_mutate_state() -> None:
    payload = finance_request("인테리어를 2천만원으로 가정해줘")
    original = copy.deepcopy(payload.state.model_dump())
    tool_runtime = runtime(payload)

    current = json.loads(asyncio.run(tool_runtime.calculate_current_plan(None)))
    simulated = json.loads(asyncio.run(tool_runtime.simulate_finance_scenario(
        None, None, None, None, None, 20_000_000, None, None, None, None, None,
        None, None, None, None, None, None,
    )))

    assert current["payload"]["funding"]["total_first_year_cash_need_krw"] == 43_200_000
    assert simulated["payload"]["funding"]["total_first_year_cash_need_krw"] == 53_200_000
    assert "인테리어비=20000000" in simulated["assumptions"]
    assert payload.state.model_dump() == original


def test_finance_tool_keeps_missing_cost_unknown() -> None:
    payload = finance_request()
    payload.state.candidates[0].management_fee_krw = None
    result = json.loads(asyncio.run(runtime(payload).calculate_current_plan(None)))

    assert result["status"] == "failed"
    assert "관리비" in result["warnings"][0]


def test_finance_comparison_and_policy_detail_stay_in_current_candidates() -> None:
    tool_runtime = runtime(finance_request())
    comparison = json.loads(asyncio.run(
        tool_runtime.compare_finance_candidates(["LEASE-1", "OUTSIDE"])
    ))
    current = json.loads(asyncio.run(tool_runtime.calculate_current_plan("LEASE-1")))
    program_id = current["payload"]["policy_candidates"][0]["program_id"]
    detail = json.loads(asyncio.run(
        tool_runtime.get_policy_candidate_detail(program_id, "LEASE-1")
    ))

    assert len(comparison["payload"]["comparisons"]) == 1
    assert "OUTSIDE" in comparison["warnings"][0]
    assert detail["status"] == "succeeded"
    assert detail["payload"]["policy_candidate"]["source_url"].startswith("http")
    assert detail["as_of"]


def test_finance_workspace_rejects_candidate_from_another_area() -> None:
    payload = finance_request().model_dump(mode="json")
    payload["state"]["candidates"][0]["area_code"] = "A-2"
    try:
        WorkspaceAgentRequest(**payload)
    except ValueError as exc:
        assert "현재 상권" in str(exc)
    else:
        raise AssertionError("candidate from another area must be rejected")
