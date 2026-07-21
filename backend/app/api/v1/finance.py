from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import get_finance_plan_service, get_lease_candidate_service
from backend.app.schemas.finance import (
    FinancePlanRequest,
    FinancePlanResponse,
    LeaseCandidateExtractRequest,
    LeaseCandidateExtractResponse,
)
from backend.app.services.finance_service import FinancePlanService
from backend.app.services.listing_service import LeaseCandidateService


router = APIRouter(tags=["finance"])


@router.post("/lease-candidates/extract", response_model=LeaseCandidateExtractResponse)
async def extract_lease_candidate(
    payload: LeaseCandidateExtractRequest,
    request: Request,
    service: LeaseCandidateService = Depends(get_lease_candidate_service),
) -> LeaseCandidateExtractResponse:
    result = await service.extract(payload)
    return LeaseCandidateExtractResponse(request_id=request.state.request_id, **result)


@router.post("/finance/plans", response_model=FinancePlanResponse)
def create_finance_plan(
    payload: FinancePlanRequest,
    request: Request,
    service: FinancePlanService = Depends(get_finance_plan_service),
) -> FinancePlanResponse:
    result = service.create_plan(payload)
    return FinancePlanResponse(request_id=request.state.request_id, **result)
