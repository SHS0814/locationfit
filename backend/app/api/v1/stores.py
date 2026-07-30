from fastapi import APIRouter, Depends, Query, Request

from backend.app.api.dependencies import get_store_service
from backend.app.schemas.store import AreaStoresResponse
from backend.app.services.store_service import CommercialStoreService

router = APIRouter(tags=["area-stores"])


@router.get("/areas/{area_code}/stores", response_model=AreaStoresResponse)
async def area_stores(
    area_code: str,
    request: Request,
    industry_code: str = Query(min_length=1),
    service: CommercialStoreService = Depends(get_store_service),
) -> AreaStoresResponse:
    result = await service.analyse(area_code, industry_code)
    return AreaStoresResponse(request_id=request.state.request_id, **result)

