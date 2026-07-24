from fastapi import Request

from backend.app.services.agent_service import LocationAgentService
from backend.app.services.recommender_service import RecommenderService
from backend.app.services.store_service import CommercialStoreService
from backend.app.services.web_research_service import WebResearchService
from backend.app.services.finance_service import FinancePlanService
from backend.app.services.listing_service import LeaseCandidateService
from backend.app.services.workspace_agent_service import WorkspaceAgentService


def get_recommender(request: Request) -> RecommenderService:
    service = getattr(request.app.state, "recommender", None)
    if service is None:
        detail = getattr(request.app.state, "startup_error", "추천 모델이 준비되지 않았습니다.")
        raise RuntimeError(detail)
    return service


def get_location_agent(request: Request) -> LocationAgentService:
    service = getattr(request.app.state, "location_agent", None)
    if service is None:
        detail = getattr(request.app.state, "startup_error", "AI 상담 서비스가 준비되지 않았습니다.")
        raise RuntimeError(detail)
    return service


def get_workspace_agent(request: Request) -> WorkspaceAgentService:
    service = getattr(request.app.state, "workspace_agent", None)
    if service is None:
        detail = getattr(request.app.state, "startup_error", "페이지 전용 AI 서비스가 준비되지 않았습니다.")
        raise RuntimeError(detail)
    return service


def get_store_service(request: Request) -> CommercialStoreService:
    service = getattr(request.app.state, "store_service", None)
    if service is None:
        detail = getattr(request.app.state, "startup_error", "상가업소 서비스가 준비되지 않았습니다.")
        raise RuntimeError(detail)
    return service


def get_web_research_service(request: Request) -> WebResearchService:
    service = getattr(request.app.state, "web_research_service", None)
    if service is None:
        detail = getattr(request.app.state, "startup_error", "웹 리서치 서비스가 준비되지 않았습니다.")
        raise RuntimeError(detail)
    return service


def get_lease_candidate_service(request: Request) -> LeaseCandidateService:
    service = getattr(request.app.state, "lease_candidate_service", None)
    if service is None:
        detail = getattr(request.app.state, "startup_error", "매물 추출 서비스가 준비되지 않았습니다.")
        raise RuntimeError(detail)
    return service


def get_finance_plan_service(request: Request) -> FinancePlanService:
    service = getattr(request.app.state, "finance_plan_service", None)
    if service is None:
        detail = getattr(request.app.state, "startup_error", "금융계획 서비스가 준비되지 않았습니다.")
        raise RuntimeError(detail)
    return service
