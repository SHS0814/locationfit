from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies import get_recommender
from backend.app.schemas.recommendation import (
    MarketGeographyRequest,
    MarketGeographyResponse,
)
from backend.app.services.recommender_service import RecommenderService

router = APIRouter(tags=["market"])


@router.post("/market-geographies", response_model=MarketGeographyResponse)
def market_geographies(
    payload: MarketGeographyRequest,
    request: Request,
    service: RecommenderService = Depends(get_recommender),
) -> MarketGeographyResponse:
    return MarketGeographyResponse(
        request_id=request.state.request_id,
        group_by=payload.group_by,
        features=service.market_geographies(
            group_by=payload.group_by,
            entity_keys=payload.entity_keys,
        ),
    )
