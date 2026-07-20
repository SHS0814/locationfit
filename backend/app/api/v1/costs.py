from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import get_recommender
from backend.app.schemas.cost import LeasePlanRequest, LeasePlanResponse
from backend.app.services.cost_provider import calculate_lease_plan
from backend.app.services.recommender_service import RecommenderService


router = APIRouter(tags=["commercial-costs"])


@router.post("/commercial-costs/lease-plan", response_model=LeasePlanResponse)
def lease_plan(
    payload: LeasePlanRequest,
    request: Request,
    service: RecommenderService = Depends(get_recommender),
) -> LeasePlanResponse:
    estimate = service.cost_provider.estimate(
        payload.area_code,
        payload.commercial_property_type,
        payload.floor,
        payload.rentable_area_sqm,
    )
    if estimate is None:
        raise ValueError("선택한 상권과 임대조건의 한국부동산원 임대료 추정치를 찾을 수 없습니다.")
    plan = calculate_lease_plan(
        estimate,
        deposit_krw=payload.deposit_krw,
        total_startup_budget_krw=payload.total_startup_budget_krw,
    )
    return LeasePlanResponse(
        request_id=request.state.request_id,
        rental_estimate=estimate.to_dict(),
        lease_plan=plan.to_dict(),
    )
