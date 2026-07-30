from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import (
    get_finance_plan_service,
    get_financial_catalog,
)
from backend.app.financial_catalog.contracts import CatalogBundle
from backend.app.schemas.finance import (
    FinancePlanRequest,
    FinancePlanResponse,
)
from backend.app.services.finance_service import FinancePlanService

router = APIRouter(tags=["finance"])


@router.post("/finance/plans", response_model=FinancePlanResponse)
def create_finance_plan(
    payload: FinancePlanRequest,
    request: Request,
    service: FinancePlanService = Depends(get_finance_plan_service),
    catalog: CatalogBundle = Depends(get_financial_catalog),
) -> FinancePlanResponse:
    result = service.create_plan(payload, catalog)
    return FinancePlanResponse(request_id=request.state.request_id, **result)
